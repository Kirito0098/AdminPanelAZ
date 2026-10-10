#!/usr/bin/env bash
# Прямой запуск uvicorn node agent для systemd (adminpanelaz-node.service).
# Env уже загружен unit’ом (EnvironmentFile=node_agent.env); здесь — mTLS и exec.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
UVICORN="$BACKEND_DIR/.venv/bin/uvicorn"

NODE_AGENT_HOST="${NODE_AGENT_HOST:-0.0.0.0}"
NODE_AGENT_PORT="${NODE_AGENT_PORT:-9100}"

if [[ ! -x "$UVICORN" ]]; then
  echo "[systemd-exec-node] не найден $UVICORN — пересоздайте venv (install / ap_ensure_venv)" >&2
  exit 1
fi

mtls_args=()
mtls_flag="${NODE_AGENT_MTLS_ENABLED:-false}"
case "${mtls_flag,,}" in
  1|true|yes)
    cert="${NODE_AGENT_MTLS_SERVER_CERT:-/etc/adminpanelaz/mtls/agent.crt}"
    key="${NODE_AGENT_MTLS_SERVER_KEY:-/etc/adminpanelaz/mtls/agent.key}"
    ca="${NODE_AGENT_MTLS_CA_CERT:-/etc/adminpanelaz/mtls/ca.crt}"
    missing=()
    for file in "$cert" "$key" "$ca"; do
      [[ -f "$file" ]] || missing+=("$file")
    done
    if (( ${#missing[@]} > 0 )); then
      echo "[systemd-exec-node] mTLS включён (NODE_AGENT_MTLS_ENABLED=${mtls_flag}), сертификатов нет: ${missing[*]}. Агент не запущен: верните файлы в /etc/adminpanelaz/mtls или выключите mTLS в backend/node_agent.env" >&2
      exit 1
    fi
    mtls_args=(
      --ssl-certfile "$cert"
      --ssl-keyfile "$key"
      --ssl-ca-certs "$ca"
      --ssl-cert-reqs 2
    )
    ;;
esac

export PYTHONPATH="${BACKEND_DIR}${PYTHONPATH:+:$PYTHONPATH}"
export NODE_AGENT_API_KEY="${NODE_AGENT_API_KEY:-change-me-node-agent-key}"
export ANTIZAPRET_PATH="${ANTIZAPRET_PATH:-/root/antizapret}"
export NODE_AGENT_PORT

cd "$BACKEND_DIR"
exec "$UVICORN" node_agent.main:app \
  --host "$NODE_AGENT_HOST" \
  --port "$NODE_AGENT_PORT" \
  "${mtls_args[@]}"
