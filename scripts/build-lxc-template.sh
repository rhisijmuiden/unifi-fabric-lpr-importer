#!/usr/bin/env bash
# Builds the Proxmox LXC container template: Debian 13 with the application installed.
# A container made from it finishes the installation on its first start (database, secret
# key, first admin account) and shows the address and the first sign-in on its console.
#
#   sudo scripts/build-lxc-template.sh [--branch main|test] [--output DIR] [--ca FILE]
#
# Needs root, mmdebstrap, zstd and a Debian archive keyring that knows Debian 13 (trixie).
# --ca adds a CA certificate during the build only (builds behind an intercepting proxy).
set -Eeuo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
BRANCH=main
OUTPUT=$HERE/dist
CA=""
KEYRING=${KEYRING:-/usr/share/keyrings/debian-archive-keyring.gpg}
MIRROR=${MIRROR:-http://deb.debian.org/debian}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --ca) CA="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
VERSION=$(cat "$HERE/VERSION")
# A fixed file name, so the "latest release" download URL never changes; the version is in the release.
NAME=debian-13-lpr-importer_amd64
[[ "$BRANCH" == test ]] && NAME=debian-13-lpr-importer-test_amd64
mkdir -p "$OUTPUT"
WORK=$(mktemp -d)
trap 'umount -R "$WORK/rootfs/proc" "$WORK/rootfs/sys" "$WORK/rootfs/dev" 2>/dev/null || true; rm -rf "$WORK"' EXIT

echo "==> Source: the current checkout, published as branch $BRANCH"
git clone --quiet --no-hardlinks "$HERE" "$WORK/app"
git -C "$WORK/app" checkout -q -B "$BRANCH" "$(git -C "$HERE" rev-parse HEAD)"
git -C "$WORK/app" remote set-url origin https://github.com/rhisijmuiden/unifi-fabric-lpr-importer.git
git -C "$WORK/app" config "branch.$BRANCH.remote" origin
git -C "$WORK/app" config "branch.$BRANCH.merge" "refs/heads/$BRANCH"
git -C "$WORK/app" update-ref "refs/remotes/origin/$BRANCH" HEAD
for ref in $(git -C "$WORK/app" for-each-ref --format='%(refname)' refs/heads refs/remotes/origin | grep -v -e "refs/heads/$BRANCH\$" -e "refs/remotes/origin/$BRANCH\$"); do
  git -C "$WORK/app" update-ref -d "$ref"
done

echo "==> Debian 13 base system"
PACKAGES=systemd-sysv,dbus,ifupdown,isc-dhcp-client,iproute2,iputils-ping,openssh-server,ca-certificates,curl,less,vim-tiny,procps,sudo,tzdata,cron,logrotate,git
mmdebstrap --variant=minbase --include="$PACKAGES" --keyring="$KEYRING" \
  --components=main --format=directory trixie "$WORK/rootfs" \
  "deb $MIRROR trixie main" "deb $MIRROR trixie-updates main" "deb http://security.debian.org/debian-security trixie-security main"

echo "==> Installing the application"
cp -a "$WORK/app" "$WORK/rootfs/opt/lpr-importer"
if [[ -n "$CA" ]]; then
  cp "$CA" "$WORK/rootfs/usr/local/share/ca-certificates/build-ca.crt"
  chroot "$WORK/rootfs" update-ca-certificates >/dev/null
fi
cp /etc/resolv.conf "$WORK/rootfs/etc/resolv.conf"
mount -t proc proc "$WORK/rootfs/proc"
mount --rbind /sys "$WORK/rootfs/sys"
mount --rbind /dev "$WORK/rootfs/dev"
# No services start inside the build.
printf '#!/bin/sh\nexit 101\n' >"$WORK/rootfs/usr/sbin/policy-rc.d"
chmod +x "$WORK/rootfs/usr/sbin/policy-rc.d"
chroot "$WORK/rootfs" env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
  ${HTTPS_PROXY:+HTTPS_PROXY=$HTTPS_PROXY https_proxy=$HTTPS_PROXY} ${HTTP_PROXY:+HTTP_PROXY=$HTTP_PROXY http_proxy=$HTTP_PROXY} \
  ${CA:+NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/build-ca.crt PIP_CERT=/etc/ssl/certs/ca-certificates.crt} \
  bash /opt/lpr-importer/install.sh --prepare --branch "$BRANCH"
umount -R "$WORK/rootfs/proc" "$WORK/rootfs/sys" "$WORK/rootfs/dev"

echo "==> Cleaning up the image"
R=$WORK/rootfs
rm -f "$R/usr/sbin/policy-rc.d"
if [[ -n "$CA" ]]; then
  rm -f "$R/usr/local/share/ca-certificates/build-ca.crt"
  chroot "$R" update-ca-certificates --fresh >/dev/null
fi
# Proxmox writes the network, host name, DNS and SSH host keys of every new container.
: >"$R/etc/machine-id"
rm -f "$R/var/lib/dbus/machine-id" "$R"/etc/ssh/ssh_host_* "$R/etc/resolv.conf" "$R/etc/hostname"
printf 'auto lo\niface lo inet loopback\n' >"$R/etc/network/interfaces"
rm -rf "$R"/var/lib/apt/lists/* "$R"/var/cache/apt/*.bin "$R"/tmp/* "$R"/var/tmp/* "$R"/root/.npm "$R"/root/.cache
find "$R/var/log" -type f -delete
echo "lpr-importer template $VERSION ($BRANCH, $(git -C "$HERE" rev-parse --short=10 HEAD)) built $(date -u +%F)" >"$R/etc/lpr-importer-template"

echo "==> Packing $NAME.tar.zst"
tar --numeric-owner --xattrs --acls -C "$R" -cf - . | zstd -q -T0 -19 -o "$OUTPUT/$NAME.tar.zst" -f
(cd "$OUTPUT" && sha256sum "$NAME.tar.zst" >"$NAME.tar.zst.sha256")
ls -lh "$OUTPUT/$NAME.tar.zst"
