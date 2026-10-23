#!/usr/bin/env bash
# Installer for UniFi Fabric License Plate Importer on Debian 13 (VM or physical server).
#
#   apt-get update -qq && apt-get install -y -qq curl && curl -fsSL https://raw.githubusercontent.com/rhisijmuiden/unifi-fabric-lpr-importer/main/install.sh | bash
#
# Without options the installer asks for the channel, HTTP or HTTPS and a restore in dialogs.
#   --branch main|test     production (main) or test channel
#   --https                HTTPS on port 8080 with a self-signed certificate
#   --cert FILE --key FILE HTTPS on port 8080 with your own certificate (PEM)
#   --http                 plain HTTP on port 8080
#   --restore              restore a backup from FTP/FTPS/SCP after installing (new server)
#   --unattended           no dialogs and no questions (plain text output)
#
# Safe to run again: existing configuration, database and accounts are kept.
set -Eeuo pipefail

REPO_URL="https://github.com/rhisijmuiden/unifi-fabric-lpr-importer.git"
BRANCH=""
APP_DIR=/opt/lpr-importer
APP_USER=lprimporter
STATE_DIR=/var/lib/lpr-importer
CONF_DIR=/etc/lpr-importer
ENV_FILE=$CONF_DIR/lpr-importer.env
TLS_DIR=$CONF_DIR/tls
LOG=/var/log/lpr-importer-install.log
PORT=8080
RESTORE=""
WEB=""          # http | selfsigned | own
CERT_FILE=""
KEY_FILE=""
UNATTENDED=0
TITLE="UniFi Fabric License Plate Importer"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    --restore) RESTORE=1; shift ;;
    --https) WEB=selfsigned; shift ;;
    --http) WEB=http; shift ;;
    --cert) CERT_FILE="$2"; WEB=own; shift 2 ;;
    --key) KEY_FILE="$2"; WEB=own; shift 2 ;;
    --unattended|--yes) UNATTENDED=1; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
[[ -z "$BRANCH" || "$BRANCH" == "main" || "$BRANCH" == "test" ]] || { echo "--branch must be main or test" >&2; exit 1; }
if [[ "$WEB" == own && ( ! -r "$CERT_FILE" || ! -r "$KEY_FILE" ) ]]; then
  echo "--cert and --key must both point to readable PEM files" >&2; exit 1
fi
[[ $EUID -eq 0 ]] || { echo "Run this installer as root (sudo)." >&2; exit 1; }

: >"$LOG"
chmod 0600 "$LOG"

# ---------------------------------------------------------------- user interface
# Dialogs and a progress bar with whiptail when a terminal is available, plain text otherwise.

UI=text
if [[ $UNATTENDED -eq 0 ]] && { : </dev/tty; } 2>/dev/null; then
  if ! command -v whiptail >/dev/null || ! command -v curl >/dev/null; then
    echo "Preparing the installer..."
    apt-get update -qq >>"$LOG" 2>&1 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq whiptail curl >>"$LOG" 2>&1 || true
  fi
  command -v whiptail >/dev/null && UI=whiptail
fi
export TERM=${TERM:-linux}
export NEWT_COLORS='root=white,blue window=black,lightgray title=blue,lightgray border=blue,lightgray button=white,blue actbutton=white,red'

STEPS=("Installing packages" "Creating the system user" "Fetching the application" "Preparing PostgreSQL"
  "Writing the configuration" "Setting up HTTP / HTTPS" "Building the application" "Starting the services"
  "Restoring a backup" "Creating the first admin account")
TOTAL=${#STEPS[@]}
STEP=0
GAUGE_PID=""

wt() { whiptail --title "$TITLE" --backtitle "Installer · Debian 13 · port $PORT" "$@" </dev/tty 3>&1 1>/dev/tty 2>&3; }

gauge_start() {
  [[ $UI == whiptail ]] || return 0
  GAUGE_FIFO=$(mktemp -u /tmp/lpr-install.XXXXXX)
  mkfifo "$GAUGE_FIFO"
  whiptail --title "$TITLE" --backtitle "Installer · Debian 13 · port $PORT" --gauge "Starting..." 12 74 0 <"$GAUGE_FIFO" >/dev/tty 2>&1 &
  GAUGE_PID=$!
  exec 4>"$GAUGE_FIFO"
}

gauge_stop() {
  [[ -n "$GAUGE_PID" ]] || return 0
  exec 4>&-
  wait "$GAUGE_PID" 2>/dev/null || true
  rm -f "$GAUGE_FIFO"
  GAUGE_PID=""
}

# step "detail": the next step of STEPS, with its number, a bar and an optional detail line.
step() {
  STEP=$((STEP + 1))
  local name=${STEPS[$((STEP - 1))]} detail=${1:-}
  echo "===== [$STEP/$TOTAL] $name $(date -Is)" >>"$LOG"
  if [[ -n "$GAUGE_PID" ]]; then
    printf 'XXX\n%d\nStep %d of %d: %s\n\n%s\nXXX\n' $(((STEP - 1) * 100 / TOTAL)) "$STEP" "$TOTAL" "$name" "$detail" >&4
  else
    printf '\n\033[1;34m==> [%d/%d] %s\033[0m\n' "$STEP" "$TOTAL" "$name"
    [[ -z "$detail" ]] || echo "    $detail"
  fi
}

# Run a command with its output in the log file.
run() { "$@" >>"$LOG" 2>&1; }

on_error() {
  local code=$?
  gauge_stop
  local tail_text
  tail_text=$(tail -n 15 "$LOG" 2>/dev/null || true)
  if [[ $UI == whiptail ]]; then
    wt --msgbox "Step $STEP of $TOTAL failed: ${STEPS[$((STEP > 0 ? STEP - 1 : 0))]}\n\nLast lines of $LOG:\n\n$tail_text" 24 100 || true
    clear >/dev/tty 2>&1 || true
  fi
  echo "Installation failed in step $STEP of $TOTAL. Full log: $LOG" >&2
  exit "$code"
}
trap on_error ERR

set_env() {  # set_env KEY VALUE: replace or add a line in the configuration file
  if grep -qE "^$1=" "$ENV_FILE"; then
    sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"
  else
    echo "$1=$2" >>"$ENV_FILE"
  fi
}
env_value() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true; }

server_ip() { hostname -I 2>/dev/null | awk '{print $1}'; }

# ---------------------------------------------------------------- questions

. /etc/os-release
if [[ "${ID:-}" != "debian" || "${VERSION_ID:-}" != "13" ]]; then
  if [[ $UI == whiptail ]]; then
    wt --yesno "This installer is made for Debian 13; this server runs ${PRETTY_NAME:-an unknown system}.\n\nContinue anyway?" 10 70 || exit 1
  else
    echo "Warning: this installer is made for Debian 13; detected ${PRETTY_NAME:-unknown}." >&2
  fi
fi

CURRENT_TLS=$(env_value LPR_TLS_CERT)
if [[ $UI == whiptail ]]; then
  wt --msgbox "Welcome.\n\nThis installs the License Plate Importer on this server: PostgreSQL, Python, Node.js, the application and its services. The web interface runs on port $PORT.\n\nExisting configuration, data and accounts are kept when you run this again." 14 74
  if [[ -z "$BRANCH" ]]; then
    BRANCH=$(wt --menu "Which channel?" 13 74 2 \
      main "Production - stable releases (recommended)" \
      test "Test - new features before they reach production") || exit 1
  fi
  if [[ -z "$WEB" ]]; then
    default=http; [[ -n "$CURRENT_TLS" ]] && default=keep
    options=(http "HTTP on port $PORT (internal network)"
      selfsigned "HTTPS on port $PORT with a self-signed certificate"
      own "HTTPS on port $PORT with my own certificate")
    [[ -n "$CURRENT_TLS" ]] && options=(keep "Keep the current HTTPS certificate" "${options[@]}")
    WEB=$(wt --default-item "$default" --menu "How is the web interface reached?\n\nUse HTTPS when an external system such as Lobster connects over the internet." 17 76 4 "${options[@]}") || exit 1
    if [[ "$WEB" == own ]]; then
      CERT_FILE=$(wt --inputbox "Path of the certificate (PEM, full chain):" 9 74 "/root/cert.pem") || exit 1
      KEY_FILE=$(wt --inputbox "Path of the private key (PEM):" 9 74 "/root/key.pem") || exit 1
      [[ -r "$CERT_FILE" && -r "$KEY_FILE" ]] || { wt --msgbox "Certificate or key not found." 8 50; exit 1; }
    fi
  fi
  if [[ -z "$RESTORE" ]]; then
    if wt --defaultno --yesno "Restore a backup after installing?\n\nChoose Yes on a new server that replaces an old one: you will be asked for the backup location (SCP, FTPS or FTP) and the backup passphrase." 12 74; then
      RESTORE=1
    else
      RESTORE=0
    fi
  fi
  case "$WEB" in http) web_text="HTTP" ;; selfsigned) web_text="HTTPS, self-signed certificate" ;; own) web_text="HTTPS, own certificate" ;; *) web_text="HTTPS, current certificate" ;; esac
  wt --yesno "Ready to install:\n\n  Channel:   $BRANCH\n  Web:       $web_text, port $PORT\n  Restore:   $([[ $RESTORE == 1 ]] && echo yes || echo no)\n  Folder:    $APP_DIR\n\nThis takes a few minutes. Continue?" 16 74 || exit 1
fi
BRANCH=${BRANCH:-main}
RESTORE=${RESTORE:-0}
WEB=${WEB:-keep}

gauge_start

# ---------------------------------------------------------------- 1. packages

step "apt-get: git, PostgreSQL, Python, Node.js, OpenSSL"
export DEBIAN_FRONTEND=noninteractive
run apt-get update -qq
run apt-get install -y -qq git curl ca-certificates sudo openssl python3 python3-venv python3-pip \
  postgresql postgresql-client nodejs npm

# ---------------------------------------------------------------- 2. user

step "$APP_USER"
id "$APP_USER" >/dev/null 2>&1 || run useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$STATE_DIR"

# ---------------------------------------------------------------- 3. application

step "Branch $BRANCH from GitHub"
if [[ -d "$APP_DIR/.git" ]]; then
  run runuser -u "$APP_USER" -- git -C "$APP_DIR" fetch --quiet origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
  run runuser -u "$APP_USER" -- git -C "$APP_DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
  run runuser -u "$APP_USER" -- git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

# ---------------------------------------------------------------- 4. database

step "Database and role $APP_USER"
run systemctl enable --now postgresql
runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$APP_USER'" | grep -q 1 \
  || run runuser -u postgres -- createuser "$APP_USER"
# A container without a generated locale gives a SQL_ASCII cluster; the application needs UTF8.
# An empty database left by an earlier failed run in SQL_ASCII is recreated.
DB_ENCODING=$(runuser -u postgres -- psql -tAc "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname='$APP_USER'")
if [[ -n "$DB_ENCODING" && "$DB_ENCODING" != UTF8 ]] \
  && ! runuser -u postgres -- psql -d "$APP_USER" -tAc "SELECT 1 FROM pg_tables WHERE schemaname='public' LIMIT 1" | grep -q 1; then
  run runuser -u postgres -- dropdb "$APP_USER"
  DB_ENCODING=""
fi
[[ -n "$DB_ENCODING" ]] \
  || run runuser -u postgres -- createdb -O "$APP_USER" -E UTF8 -T template0 --locale=C.UTF-8 "$APP_USER"

# ---------------------------------------------------------------- 5. configuration

step "$ENV_FILE"
install -d -m 0750 -o root -g "$APP_USER" "$CONF_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  cat >"$ENV_FILE" <<CONF
# UniFi Fabric License Plate Importer
LPR_DATABASE_URL=postgresql+psycopg://$APP_USER@/$APP_USER
# Encrypts stored passwords and tokens. Keep it; a backup restored elsewhere carries its own copy.
LPR_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
# Address users open in the browser; also used for the Entra SSO redirect URI.
LPR_BASE_URL=http://$(server_ip || echo localhost):$PORT
# true when the app is served over HTTPS (set by the installer).
LPR_COOKIE_SECURE=false
LPR_REPO_DIR=$APP_DIR
LPR_STATE_DIR=$STATE_DIR
LPR_FRONTEND_DIST=$APP_DIR/frontend/dist
CONF
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

# ---------------------------------------------------------------- 6. http / https

host_of_url() { local u=${1#*://}; u=${u%%/*}; echo "${u%:*}"; }
CURRENT_HOST=$(host_of_url "$(env_value LPR_BASE_URL)")
CURRENT_HOST=${CURRENT_HOST:-$(server_ip)}
case "$WEB" in
  selfsigned)
    step "Self-signed certificate for $CURRENT_HOST (valid 10 years)"
    install -d -m 0750 -o root -g "$APP_USER" "$TLS_DIR"
    SAN="DNS:$(hostname),DNS:$(hostname -f 2>/dev/null || hostname),DNS:localhost,IP:127.0.0.1"
    [[ -n "$(server_ip)" ]] && SAN="$SAN,IP:$(server_ip)"
    run openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 3650 \
      -subj "/CN=$CURRENT_HOST/O=LPR Importer" -addext "subjectAltName=$SAN" \
      -keyout "$TLS_DIR/key.pem" -out "$TLS_DIR/cert.pem"
    ;;
  own)
    step "Own certificate $CERT_FILE"
    install -d -m 0750 -o root -g "$APP_USER" "$TLS_DIR"
    install -m 0640 -o root -g "$APP_USER" "$CERT_FILE" "$TLS_DIR/cert.pem"
    install -m 0640 -o root -g "$APP_USER" "$KEY_FILE" "$TLS_DIR/key.pem"
    run openssl x509 -in "$TLS_DIR/cert.pem" -noout
    ;;
  http)
    step "Plain HTTP on port $PORT"
    ;;
  *)
    step "Unchanged"
    ;;
esac
if [[ "$WEB" == selfsigned || "$WEB" == own ]]; then
  chown root:"$APP_USER" "$TLS_DIR"/cert.pem "$TLS_DIR"/key.pem
  chmod 0640 "$TLS_DIR"/cert.pem "$TLS_DIR"/key.pem
  set_env LPR_TLS_CERT "$TLS_DIR/cert.pem"
  set_env LPR_TLS_KEY "$TLS_DIR/key.pem"
  set_env LPR_BASE_URL "https://$CURRENT_HOST:$PORT"
  set_env LPR_COOKIE_SECURE true
elif [[ "$WEB" == http ]]; then
  sed -i '/^LPR_TLS_CERT=/d;/^LPR_TLS_KEY=/d' "$ENV_FILE"
  set_env LPR_BASE_URL "http://$CURRENT_HOST:$PORT"
  set_env LPR_COOKIE_SECURE false
fi

# ---------------------------------------------------------------- 7. build

step "Python packages, web interface and database migrations (a few minutes)"
run runuser -u "$APP_USER" -- env HOME="$STATE_DIR" APP_DIR="$APP_DIR" ENV_FILE="$ENV_FILE" "$APP_DIR/scripts/build.sh"

# ---------------------------------------------------------------- 8. services

step "lpr-importer.service on port $PORT"
install -m 0644 "$APP_DIR/deploy/lpr-importer.service" /etc/systemd/system/lpr-importer.service
install -m 0644 "$APP_DIR/deploy/lpr-importer-update.service" /etc/systemd/system/lpr-importer-update.service
install -m 0440 "$APP_DIR/deploy/sudoers" /etc/sudoers.d/lpr-importer
run visudo -cf /etc/sudoers.d/lpr-importer
run systemctl daemon-reload
run systemctl enable lpr-importer.service
run systemctl restart lpr-importer.service

app_cli() {
  (cd "$APP_DIR/backend" && runuser -u "$APP_USER" -- env $(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" | xargs -d '\n') \
    "$APP_DIR/.venv/bin/python" -m app.cli "$@")
}

# ---------------------------------------------------------------- 9. restore

if [[ "$RESTORE" == 1 ]]; then
  step "Answer the questions below"
  gauge_stop
  clear >/dev/tty 2>&1 || true
  echo "Restore a backup: enter the backup location and the backup passphrase." >/dev/tty
  echo "Users, settings and vehicles come from the backup." >/dev/tty
  if app_cli restore </dev/tty >/dev/tty 2>&1; then
    run systemctl restart lpr-importer.service
  else
    echo "The restore did not finish. Try again later with: sudo bash $APP_DIR/install.sh --restore" >/dev/tty
    sleep 3
  fi
  gauge_start
else
  step "Skipped"
fi

# ---------------------------------------------------------------- 10. admin and health check

step "Waiting for the application to answer"
CREDS=$(app_cli create-admin 2>>"$LOG")
echo "$CREDS" | grep -v password >>"$LOG" || true
if [[ -n "$(env_value LPR_TLS_CERT)" ]]; then HEALTH="https://127.0.0.1:$PORT/api/health"; else HEALTH="http://127.0.0.1:$PORT/api/health"; fi
UP=0
for _ in $(seq 1 30); do
  if curl -fsSk "$HEALTH" >/dev/null 2>&1; then UP=1; break; fi
  sleep 1
done
[[ -n "$GAUGE_PID" ]] && printf 'XXX\n100\nDone\nXXX\n' >&4
gauge_stop
trap - ERR

URL=$(env_value LPR_BASE_URL)
SUMMARY="Open $URL in your browser."
[[ $UP == 1 ]] || SUMMARY="The service did not answer yet. Check: journalctl -u lpr-importer -f\nThen open $URL"
[[ -n "$(env_value LPR_TLS_CERT)" && "$WEB" == selfsigned ]] && SUMMARY="$SUMMARY\n\nThe certificate is self-signed: the browser asks once to trust it."
if echo "$CREDS" | grep -q password; then
  SUMMARY="$SUMMARY\n\nFirst sign-in (change the password afterwards):\n$(echo "$CREDS" | grep -E 'username|password')"
fi
SUMMARY="$SUMMARY\n\nConfiguration: $ENV_FILE\nLogs: journalctl -u lpr-importer -f\nInstall log: $LOG"

if [[ $UI == whiptail ]]; then
  wt --msgbox "Installation finished.\n\n$SUMMARY" 22 78 || true
  clear >/dev/tty 2>&1 || true
fi
printf '\n\033[1;32m==> Installation finished\033[0m\n'
echo -e "$SUMMARY"
