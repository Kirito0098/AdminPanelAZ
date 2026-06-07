#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="adminpanelaz-node"
UNIT_SRC="$ROOT_DIR/systemd/${SERVICE_NAME}.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
STATE_DIR="${NODE_AGENT_STATE_DIR:-/var/lib/adminpanelaz-node}"
INSTALL_USER="${INSTALL_USER:-root}"
INSTALL_GROUP="${INSTALL_GROUP:-$(id -gn "$INSTALL_USER" 2>/dev/null || echo root)}"

log() {
  echo "[install-node-systemd] $*"
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Запустите от root: sudo $0"
  exit 1
fi

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Нет unit-шаблона: $UNIT_SRC"
  exit 1
fi

if [[ ! -x "$ROOT_DIR/start_node_agent.sh" ]]; then
  chmod +x "$ROOT_DIR/start_node_agent.sh"
fi

mkdir -p "$STATE_DIR/logs" "$STATE_DIR/run"
chown -R "$INSTALL_USER:$INSTALL_GROUP" "$STATE_DIR"

log "Установка $UNIT_DST"
sed \
  -e "s|/opt/AdminPanelAZ|$ROOT_DIR|g" \
  -e "s|/var/lib/adminpanelaz-node|$STATE_DIR|g" \
  -e "s|^User=root|User=$INSTALL_USER|" \
  -e "s|^Group=root|Group=$INSTALL_GROUP|" \
  "$UNIT_SRC" >"$UNIT_DST"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

log "Установлен и включён $SERVICE_NAME"
log "Перед запуском задайте NODE_AGENT_API_KEY в $UNIT_DST"
log "Старт:   systemctl start $SERVICE_NAME"
log "Статус:  systemctl status $SERVICE_NAME"
log "Журнал:  journalctl -u $SERVICE_NAME -f"
log "Файлы:   $STATE_DIR/logs/"
