#!/usr/bin/env bash
# Служебный скрипт: установка systemd unit для proxy_agent на RU-хосте.
# proxy.sh ставит админ вручную; этот скрипт только агент панели.
set -euo pipefail

if [[ "${INSTALL_FROM_INSTALL_SH:-}" != "1" ]]; then
  echo "[install-proxy-systemd] Установка proxy_agent (systemd). proxy.sh этим скриптом не ставится." >&2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="adminpanelaz-proxy"
UNIT_SRC="$ROOT_DIR/systemd/${SERVICE_NAME}.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
STATE_DIR="${PROXY_AGENT_STATE_DIR:-/var/lib/adminpanelaz-proxy}"
INSTALL_USER="${INSTALL_USER:-root}"
INSTALL_GROUP="${INSTALL_GROUP:-$(id -gn "$INSTALL_USER" 2>/dev/null || echo root)}"

log() {
  echo "[install-proxy-systemd] $*"
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Запустите от root: sudo $0"
  exit 1
fi

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Нет unit-шаблона: $UNIT_SRC"
  exit 1
fi

chmod +x "$ROOT_DIR/scripts/systemd-exec-proxy.sh" 2>/dev/null || true

mkdir -p "$STATE_DIR/logs" "$STATE_DIR/run"
chown -R "$INSTALL_USER:$INSTALL_GROUP" "$STATE_DIR"

log "Установка $UNIT_DST"
sed \
  -e "s|/opt/AdminPanelAZ|$ROOT_DIR|g" \
  -e "s|/var/lib/adminpanelaz-proxy|$STATE_DIR|g" \
  -e "s|^User=root|User=$INSTALL_USER|" \
  -e "s|^Group=root|Group=$INSTALL_GROUP|" \
  -e "s|Environment=PROXY_AGENT_PORT=9101|Environment=PROXY_AGENT_PORT=${PROXY_AGENT_PORT:-9101}|" \
  -e "s|PROXY_AGENT_API_KEY=change-me-proxy-agent-key|PROXY_AGENT_API_KEY=${PROXY_AGENT_API_KEY:-change-me-proxy-agent-key}|" \
  -e "s|EnvironmentFile=-/opt/AdminPanelAZ/backend/proxy_agent.env|EnvironmentFile=-$ROOT_DIR/backend/proxy_agent.env|" \
  "$UNIT_SRC" >"$UNIT_DST"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

log "Установлен и включён $SERVICE_NAME"
log "EnvironmentFile: $ROOT_DIR/backend/proxy_agent.env"
log "Порт по умолчанию: ${PROXY_AGENT_PORT:-9101}"
log "Старт:   systemctl start $SERVICE_NAME"
log "Статус:  systemctl status $SERVICE_NAME"
log "Журнал:  journalctl -u $SERVICE_NAME -f"
log "Файлы:   $STATE_DIR/logs/"
