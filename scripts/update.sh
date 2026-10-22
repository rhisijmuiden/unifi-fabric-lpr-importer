#!/usr/bin/env bash
# Updates the application or switches between the production (main) and test branch.
# Started as root by lpr-importer-update.service; the web app writes the request file.
set -uo pipefail

APP_DIR=/opt/lpr-importer
APP_USER=lprimporter
STATE_DIR=/var/lib/lpr-importer
REQUEST="$STATE_DIR/update-request.json"
STATUS="$STATE_DIR/update-status.json"
LOG="$STATE_DIR/update.log"

as_app() { runuser -u "$APP_USER" -- "$@"; }

write_status() {  # state, message
  python3 - "$STATUS" "$1" "$2" "${CHANNEL:-}" "${OLD_COMMIT:-}" <<'PY'
import json, sys, datetime
path, state, message, channel, old = sys.argv[1:6]
try:
    data = json.load(open(path))
except Exception:
    data = {}
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
data.update(state=state, message=message, channel=channel, previous_commit=old, updated_at=now)
if state == "running" and message == "Starting":
    data["started_at"] = now
json.dump(data, open(path, "w"))
PY
}

exec >>"$LOG" 2>&1
echo
echo "===== $(date -Is) update requested ====="

CHANNEL=$(python3 -c "import json;print(json.load(open('$REQUEST'))['channel'])" 2>/dev/null || true)
if [[ "$CHANNEL" != "main" && "$CHANNEL" != "test" ]]; then
  write_status failed "Invalid update request"
  exit 1
fi
OLD_COMMIT=$(as_app git -C "$APP_DIR" rev-parse HEAD)
write_status running "Starting"
echo "Channel: $CHANNEL, current commit: $OLD_COMMIT"

fail() {
  echo "!! $1 - rolling back to $OLD_COMMIT"
  write_status running "Rolling back"
  as_app git -C "$APP_DIR" checkout -q -B "$PREV_BRANCH" "$OLD_COMMIT" \
    && as_app env HOME="$STATE_DIR" APP_DIR="$APP_DIR" "$APP_DIR/scripts/build.sh" \
    && systemctl restart lpr-importer.service
  write_status failed "$1. The previous version was restored."
  exit 1
}

PREV_BRANCH=$(as_app git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)

echo "==> Database snapshot before update"
mkdir -p "$STATE_DIR/pre-update"
chown "$APP_USER": "$STATE_DIR/pre-update"
SNAP="$STATE_DIR/pre-update/$(date +%Y%m%d-%H%M%S)-$OLD_COMMIT.dump"
as_app pg_dump -Fc -f "$SNAP" lprimporter || fail "Database snapshot failed"
ls -1t "$STATE_DIR"/pre-update/*.dump 2>/dev/null | tail -n +6 | xargs -r rm -f

echo "==> Fetching $CHANNEL"
as_app git -C "$APP_DIR" fetch --quiet origin "+refs/heads/$CHANNEL:refs/remotes/origin/$CHANNEL" || fail "Could not download the update"
as_app git -C "$APP_DIR" checkout -q -B "$CHANNEL" "origin/$CHANNEL" || fail "Checkout failed"
as_app git -C "$APP_DIR" branch -q --set-upstream-to="origin/$CHANNEL" "$CHANNEL" || true
# Keep the scripts executable and the systemd/sudoers files current.
install -m 0644 "$APP_DIR/deploy/lpr-importer.service" /etc/systemd/system/lpr-importer.service
install -m 0644 "$APP_DIR/deploy/lpr-importer-update.service" /etc/systemd/system/lpr-importer-update.service
install -m 0440 "$APP_DIR/deploy/sudoers" /etc/sudoers.d/lpr-importer
systemctl daemon-reload

write_status running "Building"
as_app env HOME="$STATE_DIR" APP_DIR="$APP_DIR" "$APP_DIR/scripts/build.sh" || fail "Build failed"

write_status running "Restarting"
systemctl restart lpr-importer.service || fail "Restart failed"
sleep 3
HEALTH=http://127.0.0.1:8080/api/health
grep -qE '^LPR_TLS_CERT=.+' /etc/lpr-importer/lpr-importer.env 2>/dev/null && HEALTH=https://127.0.0.1:8080/api/health
for _ in $(seq 1 20); do
  if curl -fsSk "$HEALTH" >/dev/null 2>&1; then
    NEW=$(as_app git -C "$APP_DIR" rev-parse --short=10 HEAD)
    echo "Update finished: now on $CHANNEL @ $NEW"
    write_status success "Now on $CHANNEL ($(cat "$APP_DIR/VERSION"), $NEW)"
    exit 0
  fi
  sleep 2
done
fail "The application did not come back after the update"
