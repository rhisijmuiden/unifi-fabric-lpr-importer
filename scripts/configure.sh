#!/usr/bin/env bash
# Applies the web address and HTTP/HTTPS settings of the application. Runs as root.
#
#   configure.sh --mode http|selfsigned|own|keep [--host NAME] [--cert FILE --key FILE] [--no-restart]
#   configure.sh --request      (from update.sh, i.e. lpr-importer-update.service: reads config-request.json)
#   configure.sh --console-info (rewrite the sign-in text shown on the server console)
#
# The web app cannot change these itself: the configuration file and certificates belong to root.
# With --request it also ends the first-run setup (the first password disappears from the
# console) and starts a channel switch afterwards when the setup asked for one.
set -uo pipefail

APP_DIR=${APP_DIR:-/opt/lpr-importer}
APP_USER=lprimporter
STATE_DIR=/var/lib/lpr-importer
CONF_DIR=/etc/lpr-importer
ENV_FILE=$CONF_DIR/lpr-importer.env
TLS_DIR=$CONF_DIR/tls
INITIAL=$CONF_DIR/initial-admin
REQUEST=$STATE_DIR/config-request.json
STATUS=$STATE_DIR/config-status.json
PORT=8080

MODE=keep
HOST=""
CERT_FILE=""
KEY_FILE=""
RESTART=1
FROM_REQUEST=0
CONSOLE_ONLY=0
FINISH_SETUP=0
CHANNEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --cert) CERT_FILE="$2"; shift 2 ;;
    --key) KEY_FILE="$2"; shift 2 ;;
    --no-restart) RESTART=0; shift ;;
    --request) FROM_REQUEST=1; shift ;;
    --console-info) CONSOLE_ONLY=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

set_env() {  # set_env KEY VALUE: replace or add a line in the configuration file
  if grep -qE "^$1=" "$ENV_FILE"; then
    sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"
  else
    echo "$1=$2" >>"$ENV_FILE"
  fi
}
env_value() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true; }
server_ip() { hostname -I 2>/dev/null | awk '{print $1}'; }
host_of_url() { local u=${1#*://}; u=${u%%/*}; echo "${u%:*}"; }

write_status() {  # state, message
  [[ $FROM_REQUEST == 1 ]] || return 0
  python3 - "$STATUS" "$1" "$2" <<'PY'
import datetime, json, sys
path, state, message = sys.argv[1:4]
json.dump({"state": state, "message": message,
           "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, open(path, "w"))
PY
  chown "$APP_USER": "$STATUS" 2>/dev/null || true
}

fail() {
  echo "!! $1" >&2
  write_status failed "$1"
  exit 1
}

# Text above the login prompt on the server console (Proxmox: the Console tab of the container).
# The first password is only there until the setup in the web interface is finished.
console_info() {
  local scheme=http
  [[ -n "$(env_value LPR_TLS_CERT)" ]] && scheme=https
  local text
  text="UniFi Fabric License Plate Importer
  Web interface: $scheme://\\4:$PORT"
  local configured
  configured=$(host_of_url "$(env_value LPR_BASE_URL)")
  if [[ -n "$configured" && ! "$configured" =~ ^[0-9.]+$ ]]; then
    text="$text
                 $scheme://$configured:$PORT"
  fi
  if [[ -r "$INITIAL" ]]; then
    text="$text
  Username:      $(sed -n 's/^username=//p' "$INITIAL")
  Password:      $(sed -n 's/^password=//p' "$INITIAL")
  Sign in and finish the setup in the web interface."
  fi
  mkdir -p /etc/issue.d
  printf '%s\n\n' "$text" >/etc/issue.d/lpr-importer.issue
  # Also after an SSH or console sign-in (pam_motd); \4 only works on the console, so use the address.
  printf '%s\n\n' "${text//\\4/$(server_ip || echo localhost)}" >/etc/motd
}

if [[ $FROM_REQUEST == 1 ]]; then
  exec >>"$STATE_DIR/config.log" 2>&1
  echo "===== $(date -Is) configuration requested ====="
fi

if [[ $CONSOLE_ONLY == 1 ]]; then
  console_info
  exit 0
fi

[[ -f "$ENV_FILE" ]] || fail "The configuration file $ENV_FILE does not exist"

TMP=""
cleanup() { [[ -n "$TMP" ]] && rm -rf "$TMP"; }
trap cleanup EXIT

if [[ $FROM_REQUEST == 1 ]]; then
  [[ -f "$REQUEST" ]] || fail "No configuration request"
  TMP=$(mktemp -d)
  chmod 0700 "$TMP"
  # Read the request with Python: certificate and key are written to private files, the rest to shell variables.
  eval "$(python3 - "$REQUEST" "$TMP" <<'PY'
import json, re, shlex, sys
req = json.load(open(sys.argv[1]))
tmp = sys.argv[2]
mode = req.get("mode") or "keep"
host = req.get("host") or ""
channel = req.get("channel") or ""
if mode not in ("http", "selfsigned", "own", "keep"):
    mode = "invalid"
if host and not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
    host = "invalid"
if channel not in ("", "main", "test"):
    channel = ""
print(f"MODE={shlex.quote(mode)}")
print(f"HOST={shlex.quote(host)}")
print(f"CHANNEL={shlex.quote(channel)}")
print(f"FINISH_SETUP={1 if req.get('finish_setup') else 0}")
if mode == "own":
    open(f"{tmp}/cert.pem", "w").write(req.get("cert_pem") or "")
    open(f"{tmp}/key.pem", "w").write(req.get("key_pem") or "")
    print(f"CERT_FILE={shlex.quote(tmp + '/cert.pem')}")
    print(f"KEY_FILE={shlex.quote(tmp + '/key.pem')}")
PY
)" || fail "Invalid configuration request"
  rm -f "$REQUEST"
  write_status running "Applying"
fi

[[ "$MODE" == invalid ]] && fail "Unknown web mode"
[[ "$HOST" == invalid ]] && fail "Invalid host name"

CURRENT_HOST=$(host_of_url "$(env_value LPR_BASE_URL)")
HOST=${HOST:-${CURRENT_HOST:-$(server_ip)}}
HOST=${HOST:-localhost}

case "$MODE" in
  selfsigned)
    install -d -m 0750 -o root -g "$APP_USER" "$TLS_DIR"
    SAN="DNS:$(hostname),DNS:localhost,IP:127.0.0.1"
    if [[ "$HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then SAN="$SAN,IP:$HOST"; else SAN="$SAN,DNS:$HOST"; fi
    ip=$(server_ip)
    [[ -n "$ip" && "$ip" != "$HOST" ]] && SAN="$SAN,IP:$ip"
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 3650 \
      -subj "/CN=$HOST/O=LPR Importer" -addext "subjectAltName=$SAN" \
      -keyout "$TLS_DIR/key.pem.new" -out "$TLS_DIR/cert.pem.new" >/dev/null 2>&1 \
      || fail "Could not create a certificate"
    mv -f "$TLS_DIR/cert.pem.new" "$TLS_DIR/cert.pem"
    mv -f "$TLS_DIR/key.pem.new" "$TLS_DIR/key.pem"
    ;;
  own)
    [[ -s "$CERT_FILE" && -s "$KEY_FILE" ]] || fail "Certificate or key missing"
    openssl x509 -in "$CERT_FILE" -noout 2>/dev/null || fail "The certificate is not a valid PEM certificate"
    cert_pub=$(openssl x509 -in "$CERT_FILE" -noout -pubkey 2>/dev/null)
    key_pub=$(openssl pkey -in "$KEY_FILE" -pubout 2>/dev/null) || fail "The private key is not a valid PEM key without a passphrase"
    [[ "$cert_pub" == "$key_pub" ]] || fail "The private key does not belong to the certificate"
    install -d -m 0750 -o root -g "$APP_USER" "$TLS_DIR"
    install -m 0640 -o root -g "$APP_USER" "$CERT_FILE" "$TLS_DIR/cert.pem"
    install -m 0640 -o root -g "$APP_USER" "$KEY_FILE" "$TLS_DIR/key.pem"
    ;;
esac

if [[ "$MODE" == selfsigned || "$MODE" == own ]]; then
  chown root:"$APP_USER" "$TLS_DIR"/cert.pem "$TLS_DIR"/key.pem
  chmod 0640 "$TLS_DIR"/cert.pem "$TLS_DIR"/key.pem
  set_env LPR_TLS_CERT "$TLS_DIR/cert.pem"
  set_env LPR_TLS_KEY "$TLS_DIR/key.pem"
  set_env LPR_COOKIE_SECURE true
elif [[ "$MODE" == http ]]; then
  sed -i '/^LPR_TLS_CERT=/d;/^LPR_TLS_KEY=/d' "$ENV_FILE"
  set_env LPR_COOKIE_SECURE false
fi
SCHEME=http
[[ -n "$(env_value LPR_TLS_CERT)" ]] && SCHEME=https
set_env LPR_BASE_URL "$SCHEME://$HOST:$PORT"

[[ $FINISH_SETUP == 1 ]] && rm -f "$INITIAL"
console_info

if [[ $RESTART == 1 ]] && systemctl is-enabled --quiet lpr-importer.service 2>/dev/null; then
  write_status running "Restarting"
  systemctl restart lpr-importer.service || fail "Restart failed"
  HEALTH="$SCHEME://127.0.0.1:$PORT/api/health"
  up=0
  for _ in $(seq 1 30); do
    if curl -fsSk "$HEALTH" >/dev/null 2>&1; then up=1; break; fi
    sleep 1
  done
  [[ $up == 1 ]] || fail "The application did not answer after the restart"
fi
write_status success "$SCHEME://$HOST:$PORT"

if [[ -n "$CHANNEL" ]]; then
  current=$(runuser -u "$APP_USER" -- git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  if [[ "$CHANNEL" != "$current" ]]; then
    python3 -c 'import json,sys,datetime;json.dump({"channel":sys.argv[1],"requested_by":"setup","requested_at":datetime.datetime.now(datetime.timezone.utc).isoformat()},open(sys.argv[2],"w"))' \
      "$CHANNEL" "$STATE_DIR/update-request.json"
    chown "$APP_USER": "$STATE_DIR/update-request.json"
    # Already inside lpr-importer-update.service: continue with the channel switch right here.
    exec "$APP_DIR/scripts/update.sh"
  fi
fi
exit 0
