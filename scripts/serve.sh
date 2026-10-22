#!/usr/bin/env bash
# Starts the web application on port 8080 (lpr-importer.service). HTTPS when the
# installer configured a certificate (LPR_TLS_CERT / LPR_TLS_KEY in the env file).
set -euo pipefail

APP_DIR="${LPR_REPO_DIR:-/opt/lpr-importer}"
# One worker: SSO sign-in state and rate limits are kept in memory.
args=(app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --workers 1)
if [[ -n "${LPR_TLS_CERT:-}" && -n "${LPR_TLS_KEY:-}" ]]; then
  args+=(--ssl-certfile "$LPR_TLS_CERT" --ssl-keyfile "$LPR_TLS_KEY")
fi
cd "$APP_DIR/backend"
exec "$APP_DIR/.venv/bin/uvicorn" "${args[@]}"
