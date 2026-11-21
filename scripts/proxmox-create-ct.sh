#!/usr/bin/env bash
# Creates a UniFi Fabric License Plate Importer container on a Proxmox VE host from the
# ready-made LXC template, starts it and shows the address and the first sign-in.
# Run on the Proxmox host as root:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/rhisijmuiden/unifi-fabric-lpr-importer/main/scripts/proxmox-create-ct.sh)"
#
# Options (all optional):
#   --id 120                container ID (default: next free ID)
#   --hostname lpr-importer
#   --storage local-lvm     storage for the container disk
#   --template-storage local  storage for CT templates
#   --bridge vmbr0  --vlan 10
#   --ip dhcp | --ip 10.10.4.65/24 --gw 10.10.4.1
#   --cores 2  --memory 2048  --disk 8
#   --channel main|test     production (default) or test template
set -Eeuo pipefail

REPO=rhisijmuiden/unifi-fabric-lpr-importer
CTID=""
HOSTNAME_=lpr-importer
STORAGE=local-lvm
TSTORAGE=local
BRIDGE=vmbr0
VLAN=""
IP=dhcp
GW=""
CORES=2
MEMORY=2048
DISK=8
CHANNEL=main
while [[ $# -gt 0 ]]; do
  case "$1" in
    --id) CTID="$2"; shift 2 ;;
    --hostname) HOSTNAME_="$2"; shift 2 ;;
    --storage) STORAGE="$2"; shift 2 ;;
    --template-storage) TSTORAGE="$2"; shift 2 ;;
    --bridge) BRIDGE="$2"; shift 2 ;;
    --vlan) VLAN="$2"; shift 2 ;;
    --ip) IP="$2"; shift 2 ;;
    --gw) GW="$2"; shift 2 ;;
    --cores) CORES="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --disk) DISK="$2"; shift 2 ;;
    --channel) CHANNEL="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
command -v pct >/dev/null || { echo "Run this on a Proxmox VE host." >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }

if [[ "$CHANNEL" == test ]]; then
  FILE=debian-13-lpr-importer-test_amd64.tar.zst
  URL=https://github.com/$REPO/releases/download/template-test/$FILE
else
  FILE=debian-13-lpr-importer_amd64.tar.zst
  URL=https://github.com/$REPO/releases/latest/download/$FILE
fi
NODE=$(hostname)
CTID=${CTID:-$(pvesh get /cluster/nextid)}

echo "[1/4] Downloading the template to $TSTORAGE ($FILE)"
CACHE=$(pvesm path "$TSTORAGE:vztmpl/$FILE" 2>/dev/null || true)
if [[ -n "$CACHE" ]]; then
  # Always the newest template: replace an older download.
  mkdir -p "$(dirname "$CACHE")"
  curl -fL --progress-bar -o "$CACHE.part" "$URL"
  mv -f "$CACHE.part" "$CACHE"
else
  pvesh create "/nodes/$NODE/storage/$TSTORAGE/download-url" --content vztmpl --filename "$FILE" --url "$URL" >/dev/null
fi

echo "[2/4] Creating container $CTID ($HOSTNAME_, $CORES cores, $MEMORY MB, $DISK GB on $STORAGE)"
NET="name=eth0,bridge=$BRIDGE,ip=$IP"
[[ -n "$GW" ]] && NET="$NET,gw=$GW"
[[ -n "$VLAN" ]] && NET="$NET,tag=$VLAN"
pct create "$CTID" "$TSTORAGE:vztmpl/$FILE" \
  --hostname "$HOSTNAME_" --ostype debian --unprivileged 1 --features nesting=1 \
  --cores "$CORES" --memory "$MEMORY" --swap 512 --rootfs "$STORAGE:$DISK" \
  --net0 "$NET" --onboot 1 --description "UniFi Fabric License Plate Importer" >/dev/null

echo "[3/4] Starting the container"
pct start "$CTID"

echo "[4/4] Finishing the installation inside the container (about a minute)"
for _ in $(seq 1 180); do
  if pct exec "$CTID" -- test -r /etc/lpr-importer/initial-admin 2>/dev/null \
    && ! pct exec "$CTID" -- test -e /var/lib/lpr-importer/firstboot-pending 2>/dev/null; then
    break
  fi
  sleep 2
done
ADDR=$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}')
USER_=$(pct exec "$CTID" -- sed -n 's/^username=//p' /etc/lpr-importer/initial-admin 2>/dev/null || true)
PASS=$(pct exec "$CTID" -- sed -n 's/^password=//p' /etc/lpr-importer/initial-admin 2>/dev/null || true)

line="=================================================================="
echo
echo "$line"
echo "  UniFi Fabric License Plate Importer is installed (container $CTID)"
echo
echo "  Web interface:  http://${ADDR:-<container IP>}:8080"
if [[ -n "$PASS" ]]; then
  echo "  Username:       $USER_"
  echo "  Password:       $PASS"
  echo
  echo "  Sign in and finish the setup in the web interface."
else
  echo "  The first start is not finished yet: open the Console of container $CTID"
  echo "  in Proxmox, it shows the address, username and password."
fi
echo "$line"
