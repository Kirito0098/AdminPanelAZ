#!/usr/bin/env bash
# Базовое удаление AdminPanelAZ (остановка сервисов, systemd units)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PURGE_STATE=false

log() {
  echo "[uninstall] $*"
}

warn() {
  echo "[uninstall] ВНИМАНИЕ: $*" >&2
}

usage() {
  cat <<'EOF'
Использование: sudo ./scripts/uninstall.sh [опции]

Опции:
  --purge-state   Удалить каталоги состояния (/var/lib/adminpanelaz, .runtime)
  --help          Показать справку

Останавливает daemon/start.sh, удаляет systemd units adminpanelaz и adminpanelaz-node.
Каталог проекта и backend/.env не удаляются.
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --purge-state)
        PURGE_STATE=true
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        echo "Неизвестный аргумент: $1" >&2
        usage
        exit 1
        ;;
    esac
    shift
  done
}

stop_local_daemons() {
  if [[ -x "$ROOT_DIR/start.sh" ]]; then
    log "Остановка controller (start.sh stop)..."
    "$ROOT_DIR/start.sh" stop 2>/dev/null || true
  fi
  if [[ -x "$ROOT_DIR/start_node_agent.sh" ]]; then
    log "Остановка node agent (start_node_agent.sh stop)..."
    "$ROOT_DIR/start_node_agent.sh" stop 2>/dev/null || true
  fi
}

remove_systemd_unit() {
  local name="$1"
  local unit="/etc/systemd/system/${name}.service"

  if [[ ! -f "$unit" ]]; then
    return 0
  fi

  log "Остановка и отключение $name..."
  systemctl stop "$name" 2>/dev/null || true
  systemctl disable "$name" 2>/dev/null || true
  rm -f "$unit"
  log "Удалён $unit"
}

remove_ddns_timer() {
  local timer="adminpanelaz-ddns.timer"
  local service="adminpanelaz-ddns.service"

  if [[ ! -f "/etc/systemd/system/$timer" && ! -f "/etc/systemd/system/$service" ]]; then
    return 0
  fi

  log "Удаление DDNS timer..."
  systemctl stop "$timer" 2>/dev/null || true
  systemctl disable "$timer" 2>/dev/null || true
  rm -f "/etc/systemd/system/$timer" "/etc/systemd/system/$service"
  systemctl daemon-reload
  log "DDNS timer удалён"
}

remove_nginx_site_if_present() {
  local env_file="$ROOT_DIR/backend/.env"
  local domain=""

  if [[ ! -f "$env_file" ]]; then
    return 0
  fi
  domain=$(grep -E '^DOMAIN=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '" ' || true)
  [[ -n "$domain" ]] || return 0

  local conf_base="${domain//./_}"
  local removed=false
  for path in "/etc/nginx/sites-available/${conf_base}" "/etc/nginx/sites-enabled/${conf_base}"; do
    if [[ -f "$path" || -L "$path" ]]; then
      rm -f "$path"
      removed=true
    fi
  done

  if [[ "$removed" == true ]]; then
    log "Удалена конфигурация nginx для $domain"
    if command -v nginx >/dev/null 2>&1; then
      nginx -t >/dev/null 2>&1 && systemctl reload nginx 2>/dev/null || warn "nginx не перезагружен"
    fi
  fi

  if [[ -f /etc/ssl/certs/adminpanelaz.crt ]]; then
    rm -f /etc/ssl/certs/adminpanelaz.crt /etc/ssl/private/adminpanelaz.key
    log "Удалён самоподписанный сертификат adminpanelaz"
  fi
}

purge_state_dirs() {
  local dirs=(
    /var/lib/adminpanelaz
    /var/lib/adminpanelaz-node
    "$ROOT_DIR/.runtime"
  )
  for dir in "${dirs[@]}"; do
    if [[ -d "$dir" ]]; then
      log "Удаление $dir..."
      rm -rf "$dir"
    fi
  done
}

main() {
  parse_args "$@"

  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Запустите от root: sudo $0" >&2
    exit 1
  fi

  stop_local_daemons
  remove_nginx_site_if_present
  remove_ddns_timer
  remove_systemd_unit "adminpanelaz"
  remove_systemd_unit "adminpanelaz-node"
  systemctl daemon-reload 2>/dev/null || true

  if [[ "$PURGE_STATE" == true ]]; then
    purge_state_dirs
  else
    warn "Каталоги состояния сохранены. Для удаления: sudo $0 --purge-state"
  fi

  log "Удаление завершено. Каталог проекта ($ROOT_DIR) и backend/.env не тронуты."
}

main "$@"
