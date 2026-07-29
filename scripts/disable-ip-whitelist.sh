#!/usr/bin/env bash
# Аварийное управление IP-whitelist панели (если заблокировали себя в UI).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI="$ROOT_DIR/scripts/disable-ip-whitelist.py"
VENV_PATH="${VENV_PATH:-$ROOT_DIR/backend/.venv}"

GREEN=$(printf '\033[0;32m')
YELLOW=$(printf '\033[1;33m')
RED=$(printf '\033[0;31m')
CYAN=$(printf '\033[0;36m')
NC=$(printf '\033[0m')

ui_fail() { printf "  ${RED}✗${NC}  %s\n" "$*" >&2; }
ui_info() { printf "  ${CYAN}i${NC}  %s\n" "$*"; }
ui_warn() { printf "  ${YELLOW}!${NC}  %s\n" "$*" >&2; }

usage() {
  cat <<'EOF'
Использование: sudo ./scripts/disable-ip-whitelist.sh <команда> [аргументы]

Аварийный доступ к панели, если включили whitelist и заблокировали себя.

Команды:
  status                 Показать текущие настройки
  disable                Выключить IP-ограничение и снять firewall whitelist
  add-ip <IP|CIDR>       Добавить адрес в постоянный whitelist
  temp-ip <IP> [--hours N]  Временный whitelist (по умолчанию 24 ч.)

Примеры:
  sudo ./scripts/disable-ip-whitelist.sh status
  sudo ./scripts/disable-ip-whitelist.sh disable
  sudo ./scripts/disable-ip-whitelist.sh add-ip 203.0.113.10
  sudo ./scripts/disable-ip-whitelist.sh temp-ip 203.0.113.10 --hours 6

После disable снова откройте панель и при необходимости включите whitelist в UI.
EOF
}

_pick_python() {
  if [[ -x "$VENV_PATH/bin/python" ]]; then
    printf '%s\n' "$VENV_PATH/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  return 1
}

main() {
  if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || "${1:-}" == "" ]]; then
    usage
    exit 0
  fi

  if [[ ! -f "$CLI" ]]; then
    ui_fail "Не найден $CLI"
    exit 1
  fi

  local py
  py="$(_pick_python)" || {
    ui_fail "Python не найден (нужен backend/.venv или python3)"
    exit 1
  }

  if [[ "$(id -u)" -ne 0 ]]; then
    ui_warn "Запуск без root: настройки в БД изменятся, но iptables может остаться."
    ui_info "Для полного снятия firewall: sudo $0 $*"
  fi

  exec "$py" "$CLI" "$@"
}

main "$@"
