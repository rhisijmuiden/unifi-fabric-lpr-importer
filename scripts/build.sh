#!/usr/bin/env bash
# Builds the application in place. Runs as the application user, from install.sh and update.sh.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/lpr-importer}"
ENV_FILE="${ENV_FILE:-/etc/lpr-importer/lpr-importer.env}"

echo "==> Python dependencies"
[ -x "$APP_DIR/.venv/bin/python" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt"

echo "==> Frontend build"
cd "$APP_DIR/frontend"
npm ci --no-audit --no-fund --loglevel=error
npm run build

echo "==> Database migrations"
# Read KEY=value lines literally (same format as systemd EnvironmentFile, no shell expansion).
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] && export "$line"
done <"$ENV_FILE"
cd "$APP_DIR/backend"
"$APP_DIR/.venv/bin/alembic" upgrade head
