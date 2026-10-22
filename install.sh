#!/usr/bin/env bash
# Installer for UniFi Fabric License Plate Importer on Debian 13 (VM or physical server).
#
#   curl -fsSL https://raw.githubusercontent.com/rhisijmuiden/unifi-fabric-lpr-importer/main/install.sh | sudo bash
#   sudo bash install.sh --branch test
#
# Safe to run again: existing configuration, database and accounts are kept.
set -euo pipefail

REPO_URL="https://github.com/rhisijmuiden/unifi-fabric-lpr-importer.git"
BRANCH="main"
APP_DIR=/opt/lpr-importer
APP_USER=lprimporter
STATE_DIR=/var/lib/lpr-importer
CONF_DIR=/etc/lpr-importer
ENV_FILE=$CONF_DIR/lpr-importer.env
PORT=8080

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
[[ "$BRANCH" == "main" || "$BRANCH" == "test" ]] || { echo "--branch must be main or test" >&2; exit 1; }

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "Run this installer as root (sudo)." >&2; exit 1; }
. /etc/os-release
if [[ "${ID:-}" != "debian" || "${VERSION_ID:-}" != "13" ]]; then
  echo "Warning: this installer is made for Debian 13; detected ${PRETTY_NAME:-unknown}." >&2
fi

say "Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates sudo python3 python3-venv python3-pip \
  postgresql postgresql-client nodejs npm >/dev/null

say "Creating system user $APP_USER"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$STATE_DIR"

say "Fetching the application ($BRANCH)"
if [[ -d "$APP_DIR/.git" ]]; then
  runuser -u "$APP_USER" -- git -C "$APP_DIR" fetch --quiet origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
  runuser -u "$APP_USER" -- git -C "$APP_DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
  runuser -u "$APP_USER" -- git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

say "Preparing PostgreSQL"
systemctl enable --now postgresql >/dev/null
runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$APP_USER'" | grep -q 1 \
  || runuser -u postgres -- createuser "$APP_USER"
runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='$APP_USER'" | grep -q 1 \
  || runuser -u postgres -- createdb -O "$APP_USER" "$APP_USER"

say "Writing configuration"
install -d -m 0750 -o root -g "$APP_USER" "$CONF_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  cat >"$ENV_FILE" <<CONF
# UniFi Fabric License Plate Importer
LPR_DATABASE_URL=postgresql+psycopg://$APP_USER@/$APP_USER
LPR_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
# Address users open in the browser; also used for the Entra SSO redirect URI.
LPR_BASE_URL=http://${IP:-localhost}:$PORT
# Set to true when the app is served over HTTPS (e.g. behind a reverse proxy).
LPR_COOKIE_SECURE=false
LPR_REPO_DIR=$APP_DIR
LPR_STATE_DIR=$STATE_DIR
LPR_FRONTEND_DIST=$APP_DIR/frontend/dist
CONF
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

say "Building (this can take a few minutes)"
runuser -u "$APP_USER" -- env HOME="$STATE_DIR" APP_DIR="$APP_DIR" ENV_FILE="$ENV_FILE" "$APP_DIR/scripts/build.sh"

say "Installing services"
install -m 0644 "$APP_DIR/deploy/lpr-importer.service" /etc/systemd/system/lpr-importer.service
install -m 0644 "$APP_DIR/deploy/lpr-importer-update.service" /etc/systemd/system/lpr-importer-update.service
install -m 0440 "$APP_DIR/deploy/sudoers" /etc/sudoers.d/lpr-importer
visudo -cf /etc/sudoers.d/lpr-importer >/dev/null
systemctl daemon-reload
systemctl enable --now lpr-importer.service >/dev/null
systemctl restart lpr-importer.service

say "Creating the first admin account"
CREDS=$(cd "$APP_DIR/backend" && runuser -u "$APP_USER" -- env $(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" | xargs -d '\n') \
  "$APP_DIR/.venv/bin/python" -m app.cli create-admin)
LPR_BASE_URL=$(grep -E '^LPR_BASE_URL=' "$ENV_FILE" | cut -d= -f2-)
echo "$CREDS"

for _ in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done

say "Done"
echo "Open $LPR_BASE_URL in your browser."
echo "Configuration: $ENV_FILE   Logs: journalctl -u lpr-importer -f"
