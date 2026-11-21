#!/usr/bin/env bash
# Installer for UniFi Fabric License Plate Importer on a bare Debian 13 system:
# a physical server, a VM or a container (Proxmox LXC).
#
#   apt-get update -qq && apt-get install -y -qq curl && curl -fsSL https://raw.githubusercontent.com/rhisijmuiden/unifi-fabric-lpr-importer/main/install.sh | bash
#
# It asks nothing: at the end it shows the address of the web interface and the first admin
# account. Everything else (web address, HTTPS, channel, restore) is set up in the web interface.
#
#   --branch main|test     production (main, default) or test channel
#   --https                HTTPS on port 8080 with a self-signed certificate
#   --cert FILE --key FILE HTTPS on port 8080 with your own certificate (PEM)
#   --http                 plain HTTP on port 8080
#   --restore              restore a backup from FTP/FTPS/SCP after installing (asks for the location)
#
# Safe to run again: existing configuration, database and accounts are kept.
# Internal: --prepare builds the Proxmox LXC template, --firstboot finishes it on first start.
set -Eeuo pipefail

REPO_URL="https://github.com/rhisijmuiden/unifi-fabric-lpr-importer.git"
BRANCH=""
APP_DIR=/opt/lpr-importer
APP_USER=lprimporter
STATE_DIR=/var/lib/lpr-importer
CONF_DIR=/etc/lpr-importer
ENV_FILE=$CONF_DIR/lpr-importer.env
INITIAL=$CONF_DIR/initial-admin
LOG=/var/log/lpr-importer-install.log
PORT=8080
RESTORE=0
WEB=keep        # keep | http | selfsigned | own
CERT_FILE=""
KEY_FILE=""
STAGE=full      # full | prepare | firstboot

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    --restore) RESTORE=1; shift ;;
    --https) WEB=selfsigned; shift ;;
    --http) WEB=http; shift ;;
    --cert) CERT_FILE="$2"; WEB=own; shift 2 ;;
    --key) KEY_FILE="$2"; WEB=own; shift 2 ;;
    --prepare) STAGE=prepare; shift ;;
    --firstboot) STAGE=firstboot; shift ;;
    --unattended|--yes) shift ;;  # accepted for older scripts: the installer never asks anything
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
[[ -z "$BRANCH" || "$BRANCH" == "main" || "$BRANCH" == "test" ]] || { echo "--branch must be main or test" >&2; exit 1; }
if [[ "$WEB" == own && ( ! -r "$CERT_FILE" || ! -r "$KEY_FILE" ) ]]; then
  echo "--cert and --key must both point to readable PEM files" >&2; exit 1
fi
[[ $EUID -eq 0 ]] || { echo "Run this installer as root (sudo)." >&2; exit 1; }

touch "$LOG"
chmod 0600 "$LOG"
echo "===== $(date -Is) install.sh stage=$STAGE $*" >>"$LOG"
export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8

# ---------------------------------------------------------------- helpers

STEP=0
TOTAL=8
[[ $STAGE == prepare ]] && TOTAL=5
[[ $STAGE == firstboot ]] && TOTAL=4
step() {
  STEP=$((STEP + 1))
  echo "===== [$STEP/$TOTAL] $1 $(date -Is)" >>"$LOG"
  printf '[%d/%d] %s\n' "$STEP" "$TOTAL" "$1"
}
run() { "$@" >>"$LOG" 2>&1; }

on_error() {
  local code=$?
  echo >&2
  echo "Installation failed in step $STEP of $TOTAL. Last lines of $LOG:" >&2
  tail -n 15 "$LOG" >&2 || true
  exit "$code"
}
trap on_error ERR

env_value() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true; }
server_ip() { hostname -I 2>/dev/null | awk '{print $1}'; }

app_cli() {
  (cd "$APP_DIR/backend" && runuser -u "$APP_USER" -- env $(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" | xargs -d '\n') \
    "$APP_DIR/.venv/bin/python" -m app.cli "$@")
}

. /etc/os-release
if [[ "${ID:-}" != "debian" || "${VERSION_ID:-}" != "13" ]]; then
  echo "Warning: this installer is made for Debian 13; detected ${PRETTY_NAME:-unknown}. Continuing." >&2
fi

# ---------------------------------------------------------------- steps

install_packages() {
  step "Installing packages (PostgreSQL, Python, Node.js)"
  run apt-get update -qq
  run apt-get install -y -qq --no-install-recommends git curl ca-certificates sudo openssl \
    python3 python3-venv python3-pip postgresql postgresql-client nodejs npm
}

create_user() {
  id "$APP_USER" >/dev/null 2>&1 || run useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$APP_USER"
  install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$STATE_DIR"
}

fetch_app() {
  local branch=$1
  step "Fetching the application ($branch)"
  create_user
  if [[ $STAGE == prepare && -d "$APP_DIR/.git" ]]; then
    # The template build copied in the exact commit it builds.
    chown -R "$APP_USER": "$APP_DIR"
  elif [[ -d "$APP_DIR/.git" ]]; then
    run runuser -u "$APP_USER" -- git -C "$APP_DIR" fetch --quiet origin "+refs/heads/$branch:refs/remotes/origin/$branch"
    run runuser -u "$APP_USER" -- git -C "$APP_DIR" checkout -q -B "$branch" "origin/$branch"
  else
    install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
    run runuser -u "$APP_USER" -- git clone --quiet --branch "$branch" "$REPO_URL" "$APP_DIR"
  fi
}

prepare_database() {
  step "Preparing the database"
  # The LXC template ships without a cluster, so every container gets its own (UTF-8) one.
  if ! ls /etc/postgresql/*/main/postgresql.conf >/dev/null 2>&1; then
    local version
    version=$(ls /usr/lib/postgresql | sort -V | tail -n1)
    run pg_createcluster --locale=C.UTF-8 "$version" main
  fi
  run systemctl enable postgresql
  run systemctl start postgresql
  local cluster
  cluster=$(ls -d /etc/postgresql/*/main | head -n1 | cut -d/ -f4)
  run systemctl start "postgresql@$cluster-main"
  for _ in $(seq 1 30); do
    runuser -u postgres -- psql -tAc "SELECT 1" >/dev/null 2>&1 && break
    sleep 1
  done
  runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$APP_USER'" | grep -q 1 \
    || run runuser -u postgres -- createuser "$APP_USER"
  # A container without a generated locale gives a SQL_ASCII cluster; the application needs UTF8.
  # An empty database left by an earlier failed run in SQL_ASCII is recreated.
  local encoding
  encoding=$(runuser -u postgres -- psql -tAc "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname='$APP_USER'")
  if [[ -n "$encoding" && "$encoding" != UTF8 ]] \
    && ! runuser -u postgres -- psql -d "$APP_USER" -tAc "SELECT 1 FROM pg_tables WHERE schemaname='public' LIMIT 1" | grep -q 1; then
    run runuser -u postgres -- dropdb "$APP_USER"
    encoding=""
  fi
  [[ -n "$encoding" ]] \
    || run runuser -u postgres -- createdb -O "$APP_USER" -E UTF8 -T template0 --locale=C.UTF-8 "$APP_USER"
}

write_config() {
  step "Writing the configuration"
  create_user
  install -d -m 0750 -o root -g "$APP_USER" "$CONF_DIR"
  if [[ ! -f "$ENV_FILE" ]]; then
    cat >"$ENV_FILE" <<CONF
# UniFi Fabric License Plate Importer
LPR_DATABASE_URL=postgresql+psycopg://$APP_USER@/$APP_USER
# Encrypts stored passwords and tokens. Keep it; a backup restored elsewhere carries its own copy.
LPR_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
# Address users open in the browser; also used for the Entra SSO redirect URI. Change it in the web interface.
LPR_BASE_URL=http://$(server_ip || echo localhost):$PORT
# true when the app is served over HTTPS.
LPR_COOKIE_SECURE=false
LPR_REPO_DIR=$APP_DIR
LPR_STATE_DIR=$STATE_DIR
LPR_FRONTEND_DIST=$APP_DIR/frontend/dist
CONF
  fi
  chown root:"$APP_USER" "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  local args=(--mode "$WEB" --no-restart)
  [[ "$WEB" == own ]] && args+=(--cert "$CERT_FILE" --key "$KEY_FILE")
  run "$APP_DIR/scripts/configure.sh" "${args[@]}"
}

build_app() {
  step "Building the application (a few minutes)"
  run runuser -u "$APP_USER" -- env HOME="$STATE_DIR" APP_DIR="$APP_DIR" ENV_FILE="$ENV_FILE" "$@" "$APP_DIR/scripts/build.sh"
}

install_units() {
  install -m 0644 "$APP_DIR/deploy/lpr-importer.service" /etc/systemd/system/lpr-importer.service
  install -m 0644 "$APP_DIR/deploy/lpr-importer-update.service" /etc/systemd/system/lpr-importer-update.service
  install -m 0440 "$APP_DIR/deploy/sudoers" /etc/sudoers.d/lpr-importer
  run visudo -cf /etc/sudoers.d/lpr-importer
}

migrate() {
  (cd "$APP_DIR/backend" && run runuser -u "$APP_USER" -- env $(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" | xargs -d '\n') \
    "$APP_DIR/.venv/bin/alembic" upgrade head)
}

# Creates the first admin account when there is none; remembers it for the console until the setup is done.
create_admin() {
  local creds
  creds=$(app_cli create-admin 2>>"$LOG")
  if echo "$creds" | grep -q 'password:'; then
    ADMIN_USER=$(echo "$creds" | sed -n 's/^ *username: //p')
    ADMIN_PASSWORD=$(echo "$creds" | sed -n 's/^ *password: //p')
    umask 077
    printf 'username=%s\npassword=%s\n' "$ADMIN_USER" "$ADMIN_PASSWORD" >"$INITIAL"
    umask 022
  fi
  echo "admin account: ${ADMIN_USER:-existing}" >>"$LOG"
}

wait_for_app() {
  local scheme=http
  [[ -n "$(env_value LPR_TLS_CERT)" ]] && scheme=https
  for _ in $(seq 1 60); do
    curl -fsSk "$scheme://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

summary() {
  local up=$1 scheme=http host
  [[ -n "$(env_value LPR_TLS_CERT)" ]] && scheme=https
  host=$(server_ip)
  host=${host:-localhost}
  local line="=================================================================="
  echo
  echo "$line"
  echo "  UniFi Fabric License Plate Importer is installed"
  echo
  echo "  Web interface:  $scheme://$host:$PORT"
  if [[ -n "${ADMIN_PASSWORD:-}" ]]; then
    echo "  Username:       $ADMIN_USER"
    echo "  Password:       $ADMIN_PASSWORD"
    echo
    echo "  Sign in and finish the setup in the web interface."
  else
    echo "  Sign in with your existing account."
  fi
  if [[ $up != 1 ]]; then
    echo
    echo "  The web interface is still starting. Log: journalctl -u lpr-importer -f"
  fi
  echo "$line"
}

# ---------------------------------------------------------------- stages

case "$STAGE" in
  prepare)
    # Inside the template image (chroot, no running systemd): everything except the database.
    install_packages
    fetch_app "${BRANCH:-main}"
    build_app LPR_SKIP_MIGRATIONS=1
    step "Preparing the first start"
    install_units
    install -m 0644 "$APP_DIR/deploy/lpr-importer-firstboot.service" /etc/systemd/system/lpr-importer-firstboot.service
    run systemctl enable lpr-importer.service lpr-importer-firstboot.service postgresql.service
    touch "$STATE_DIR/firstboot-pending"
    # Every container creates its own database cluster on its first start.
    for conf in /etc/postgresql/*/main; do
      [[ -d "$conf" ]] && run pg_dropcluster "$(echo "$conf" | cut -d/ -f4)" main
    done
    step "Cleaning up"
    rm -rf "$APP_DIR/frontend/node_modules" "$STATE_DIR/.npm" "$STATE_DIR/.cache"
    run apt-get clean
    rm -rf /var/lib/apt/lists/*
    echo "Template prepared."
    exit 0
    ;;
  firstboot)
    # First start of a container made from the template: offline, nothing to download.
    for _ in $(seq 1 30); do [[ -n "$(server_ip)" ]] && break; sleep 1; done
    prepare_database
    write_config
    step "Database migrations"
    migrate
    step "Creating the first admin account"
    create_admin
    "$APP_DIR/scripts/configure.sh" --console-info
    rm -f "$STATE_DIR/firstboot-pending"
    # lpr-importer.service starts after this unit (it is ordered after it).
    summary 1
    exit 0
    ;;
esac

install_packages
# Without --branch an existing installation stays on its channel; a new one gets production.
if [[ -z "$BRANCH" && -d "$APP_DIR/.git" ]]; then
  BRANCH=$(runuser -u "$APP_USER" -- git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  [[ "$BRANCH" == main || "$BRANCH" == test ]] || BRANCH=main
fi
fetch_app "${BRANCH:-main}"
prepare_database
write_config
build_app
step "Starting the service on port $PORT"
install_units
rm -f /etc/systemd/system/lpr-importer-firstboot.service "$STATE_DIR/firstboot-pending"
run systemctl daemon-reload
run systemctl enable lpr-importer.service
run systemctl restart lpr-importer.service

if [[ "$RESTORE" == 1 ]]; then
  step "Restoring a backup"
  echo "    Enter the backup location and the backup passphrase. Users, settings and vehicles come from the backup."
  if app_cli restore </dev/tty; then
    run systemctl restart lpr-importer.service
  else
    echo "    The restore did not finish. Restore later from Backup & restore in the web interface."
  fi
else
  step "No backup to restore (restore one from the web interface if needed)"
fi

step "Creating the first admin account"
create_admin
"$APP_DIR/scripts/configure.sh" --console-info >>"$LOG" 2>&1 || true
UP=0
wait_for_app && UP=1
trap - ERR
summary "$UP"
