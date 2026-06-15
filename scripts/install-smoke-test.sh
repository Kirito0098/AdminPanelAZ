#!/usr/bin/env bash
# Smoke-test установки (non-interactive, panel-only, systemd). Вызывается из CI и вручную.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[smoke] Запустите от root: sudo $0" >&2
  exit 1
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
if [[ -f "$ROOT_DIR/backend/.env" ]]; then
  val="$(grep -E '^BACKEND_PORT=' "$ROOT_DIR/backend/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  [[ -n "$val" ]] && BACKEND_PORT="$val"
fi

log() { echo "[smoke] $*"; }

log "Non-interactive install: panel-only, systemd, minimal profile..."
"$ROOT_DIR/install.sh" --non-interactive --with-systemd -y --force

log "systemd: adminpanelaz"
systemctl is-active --quiet adminpanelaz

log "GET /api/health"
curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null

log "GET /api/health/deep"
curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/health/deep" | grep -q '"status"'

log "GET / (frontend static)"
code="$(curl -fsS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${BACKEND_PORT}/")"
if [[ "$code" != "200" ]]; then
  echo "[smoke] ОШИБКА: ожидался HTTP 200, получен $code" >&2
  exit 1
fi

log "OK — установка и health-check пройдены"
