#!/usr/bin/env bash
# Переустановка установленных systemd unit’ов из шаблонов репо (после git pull / UI «Обновить»).
# Нужен при миграции 2.19+: старые ExecStart=…/start.sh; без refresh/shim restart падает.
# Не перезапускает сервисы — caller делает systemctl restart.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PANEL_UNIT="/etc/systemd/system/adminpanelaz.service"
NODE_UNIT="/etc/systemd/system/adminpanelaz-node.service"
DO_PANEL="${REFRESH_PANEL:-1}"
DO_NODE="${REFRESH_NODE:-1}"

log() {
  echo "[refresh-systemd] $*"
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

_unit_field() {
  local unit="$1" key="$2"
  [[ -f "$unit" ]] || return 0
  sed -n "s/^${key}=//p" "$unit" | head -1
}

_unit_env() {
  local unit="$1" key="$2"
  [[ -f "$unit" ]] || return 0
  sed -n "s/^Environment=${key}=//p" "$unit" | head -1
}

_env_file_value() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 0
  sed -n "s/^${key}=//p" "$file" | head -1
}

refreshed=0

if [[ "$DO_PANEL" == "1" && -f "$PANEL_UNIT" ]]; then
  user="$(_unit_field "$PANEL_UNIT" User)"
  group="$(_unit_field "$PANEL_UNIT" Group)"
  state="$(_unit_env "$PANEL_UNIT" ADMINPANELAZ_STATE_DIR)"
  log "Обновление unit adminpanelaz из шаблона репо…"
  INSTALL_FROM_INSTALL_SH=1 \
    INSTALL_USER="${user:-root}" \
    INSTALL_GROUP="${group:-root}" \
    ADMINPANELAZ_STATE_DIR="${state:-/var/lib/adminpanelaz}" \
    "$ROOT_DIR/scripts/install-systemd.sh"
  refreshed=1
fi

if [[ "$DO_NODE" == "1" && -f "$NODE_UNIT" ]]; then
  user="$(_unit_field "$NODE_UNIT" User)"
  group="$(_unit_field "$NODE_UNIT" Group)"
  state="$(_unit_env "$NODE_UNIT" NODE_AGENT_STATE_DIR)"
  port="$(_unit_env "$NODE_UNIT" NODE_AGENT_PORT)"
  api_key="$(_unit_env "$NODE_UNIT" NODE_AGENT_API_KEY)"
  node_env="$ROOT_DIR/backend/node_agent.env"
  if [[ -z "$api_key" || "$api_key" == "change-me-node-agent-key" ]]; then
    api_key="$(_env_file_value "$node_env" NODE_AGENT_API_KEY)"
  fi
  if [[ -z "$port" ]]; then
    port="$(_env_file_value "$node_env" NODE_AGENT_PORT)"
  fi
  log "Обновление unit adminpanelaz-node из шаблона репо…"
  INSTALL_FROM_INSTALL_SH=1 \
    INSTALL_USER="${user:-root}" \
    INSTALL_GROUP="${group:-root}" \
    NODE_AGENT_STATE_DIR="${state:-/var/lib/adminpanelaz-node}" \
    NODE_AGENT_PORT="${port:-9100}" \
    NODE_AGENT_API_KEY="${api_key:-change-me-node-agent-key}" \
    "$ROOT_DIR/scripts/install-node-systemd.sh"
  refreshed=1
fi

if [[ "$refreshed" -eq 0 ]]; then
  log "Установленных unit’ов не найдено — пропуск"
else
  log "daemon-reload уже выполнен install-скриптами"
fi
