#!/usr/bin/env bash
# Прямой запуск uvicorn панели для systemd (adminpanelaz.service).
# Env уже загружен unit’ом (EnvironmentFile=backend/.env); здесь — SSL/workers и exec.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
UVICORN="$BACKEND_DIR/.venv/bin/uvicorn"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
USE_HTTPS="${USE_HTTPS:-false}"
SSL_CERT="${SSL_CERT:-}"
SSL_KEY="${SSL_KEY:-}"

if [[ ! -x "$UVICORN" ]]; then
  echo "[systemd-exec-panel] не найден $UVICORN — пересоздайте venv (install / ap_ensure_venv)" >&2
  exit 1
fi

export SERVE_FRONTEND="${SERVE_FRONTEND:-true}"
export FRONTEND_DIST_PATH="${FRONTEND_DIST_PATH:-$ROOT_DIR/frontend/dist}"

ssl_args=()
case "${USE_HTTPS,,}" in
  true|1|yes|on)
    if [[ -n "$SSL_CERT" && -n "$SSL_KEY" && -f "$SSL_CERT" && -f "$SSL_KEY" ]]; then
      ssl_args=(--ssl-certfile "$SSL_CERT" --ssl-keyfile "$SSL_KEY")
    else
      echo "[systemd-exec-panel] USE_HTTPS=true, но SSL_CERT/SSL_KEY не найдены — запуск без TLS" >&2
    fi
    ;;
esac

workers_args=()
if [[ "$UVICORN_WORKERS" =~ ^[0-9]+$ ]] && (( UVICORN_WORKERS > 1 )); then
  workers_args=(--workers "$UVICORN_WORKERS")
fi

cd "$BACKEND_DIR"
exec "$UVICORN" app.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  --proxy-headers \
  --forwarded-allow-ips="$FORWARDED_ALLOW_IPS" \
  "${ssl_args[@]}" \
  "${workers_args[@]}"
