#!/usr/bin/env bash
# Прямой запуск uvicorn proxy agent для systemd (adminpanelaz-proxy.service).
# Env уже загружен unit’ом (EnvironmentFile=proxy_agent.env); здесь — mTLS и exec.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
UVICORN="$BACKEND_DIR/.venv/bin/uvicorn"

PROXY_AGENT_HOST="${PROXY_AGENT_HOST:-0.0.0.0}"
PROXY_AGENT_PORT="${PROXY_AGENT_PORT:-9101}"

if [[ ! -x "$UVICORN" ]]; then
  echo "[systemd-exec-proxy] не найден $UVICORN — пересоздайте venv (install / ap_ensure_venv)" >&2
  exit 1
fi

mtls_args=()
if [[ "${PROXY_AGENT_MTLS_ENABLED:-false}" == "true" ]]; then
  cert="${PROXY_AGENT_MTLS_SERVER_CERT:-/etc/adminpanelaz/mtls/agent.crt}"
  key="${PROXY_AGENT_MTLS_SERVER_KEY:-/etc/adminpanelaz/mtls/agent.key}"
  ca="${PROXY_AGENT_MTLS_CA_CERT:-/etc/adminpanelaz/mtls/ca.crt}"
  if [[ -f "$cert" && -f "$key" && -f "$ca" ]]; then
    mtls_args=(
      --ssl-certfile "$cert"
      --ssl-keyfile "$key"
      --ssl-ca-certs "$ca"
      --ssl-cert-reqs 2
    )
  else
    echo "[systemd-exec-proxy] PROXY_AGENT_MTLS_ENABLED=true, но cert/key/ca не найдены — без mTLS" >&2
  fi
fi

export PYTHONPATH="${BACKEND_DIR}${PYTHONPATH:+:$PYTHONPATH}"
export PROXY_AGENT_API_KEY="${PROXY_AGENT_API_KEY:-change-me-proxy-agent-key}"
export PROXY_AGENT_PORT

cd "$BACKEND_DIR"
exec "$UVICORN" proxy_agent.main:app \
  --host "$PROXY_AGENT_HOST" \
  --port "$PROXY_AGENT_PORT" \
  "${mtls_args[@]}"
