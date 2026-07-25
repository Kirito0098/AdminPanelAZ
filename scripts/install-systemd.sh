#!/usr/bin/env bash
# Служебный скрипт: вызывается из install.sh. Для установки используйте: sudo ./install.sh
set -euo pipefail

if [[ "${INSTALL_FROM_INSTALL_SH:-}" != "1" ]]; then
  echo "[install-systemd] ВНИМАНИЕ: единая установка — sudo ./install.sh" >&2
  echo "[install-systemd] Этот скрипт — служебный (systemd unit). Мастер установки в install.sh." >&2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="adminpanelaz"
UNIT_SRC="$ROOT_DIR/systemd/${SERVICE_NAME}.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
INSTALL_USER="${INSTALL_USER:-root}"
INSTALL_GROUP="${INSTALL_GROUP:-$(id -gn "$INSTALL_USER" 2>/dev/null || echo root)}"

log() {
  echo "[install-systemd] $*"
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Missing unit template: $UNIT_SRC"
  exit 1
fi

chmod +x "$ROOT_DIR/scripts/systemd-exec-panel.sh" 2>/dev/null || true
chmod +x "$ROOT_DIR/start.sh" 2>/dev/null || true

STATE_DIR="${ADMINPANELAZ_STATE_DIR:-/var/lib/adminpanelaz}"
mkdir -p "$STATE_DIR/logs" "$STATE_DIR/run"
chown -R "$INSTALL_USER:$INSTALL_GROUP" "$STATE_DIR"

log "Installing $UNIT_DST"
sed \
  -e "s|/opt/AdminPanelAZ|$ROOT_DIR|g" \
  -e "s|/var/lib/adminpanelaz|$STATE_DIR|g" \
  -e "s|^User=root|User=$INSTALL_USER|" \
  -e "s|^Group=root|Group=$INSTALL_GROUP|" \
  -e "s|EnvironmentFile=-/opt/AdminPanelAZ/backend/.env|EnvironmentFile=-$ROOT_DIR/backend/.env|" \
  "$UNIT_SRC" >"$UNIT_DST"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

log "Installed and enabled $SERVICE_NAME"
log "Start:   systemctl start $SERVICE_NAME"
log "Status:  systemctl status $SERVICE_NAME"
log "Logs:    journalctl -u $SERVICE_NAME -f"
log "         $STATE_DIR/logs/"
