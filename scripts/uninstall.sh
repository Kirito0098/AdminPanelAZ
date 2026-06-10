#!/usr/bin/env bash
# Удаление AdminPanelAZ (остановка сервисов, systemd units, опционально — состояние и каталог проекта)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="AdminPanelAZ"

PURGE_STATE=false
PURGE_REPO=false
REMOVE_NGINX=false
REMOVE_FIREWALL=false
REMOVE_ENV=false
REMOVE_BACKUPS=false
REMOVE_SYSTEM_CONFIG=false
YES=false
SKIP_CONFIRM=false

log() {
  echo "[uninstall] $*"
}

warn() {
  echo "[uninstall] ВНИМАНИЕ: $*" >&2
}

usage() {
  cat <<EOF
Использование: sudo ./scripts/uninstall.sh [опции]

Опции:
  --purge-state         Удалить каталоги состояния (/var/lib/adminpanelaz, /var/lib/adminpanelaz-node, .runtime)
  --purge               Удалить каталог проекта ($ROOT_DIR) — необратимо
  --remove-nginx        Удалить конфигурацию nginx сайта (по DOMAIN из backend/.env)
  --remove-firewall     Удалить правила firewall AdminPanelAZ (ufw и iptables)
  --remove-env          Удалить backend/.env и backend/node_agent.env
  --remove-backups      Удалить каталог бэкапов (BACKUP_ROOT из backend/.env)
  --remove-system-config  Удалить /etc/adminpanelaz (ddns.env, mtls, node_agent.env)
  -y, --yes             Без интерактивных подтверждений
  --skip-confirm        Не спрашивать подтверждение (вызывается из install.sh после своего диалога)
  --help                Показать справку

По умолчанию останавливает сервисы и удаляет systemd units (adminpanelaz, adminpanelaz-node, DDNS timer).
Каталог проекта, backend/.env и данные AntiZapret не удаляются без явных флагов.

Примеры:
  sudo ./scripts/uninstall.sh
  sudo ./scripts/uninstall.sh --purge-state --remove-nginx -y
  sudo ./scripts/uninstall.sh --purge-state --purge --remove-env -y
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --purge-state)
        PURGE_STATE=true
        ;;
      --purge)
        PURGE_REPO=true
        ;;
      --remove-nginx)
        REMOVE_NGINX=true
        ;;
      --remove-firewall)
        REMOVE_FIREWALL=true
        ;;
      --remove-env)
        REMOVE_ENV=true
        ;;
      --remove-backups)
        REMOVE_BACKUPS=true
        ;;
      --remove-system-config)
        REMOVE_SYSTEM_CONFIG=true
        ;;
      -y|--yes)
        YES=true
        ;;
      --skip-confirm)
        SKIP_CONFIRM=true
        YES=true
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

confirm_destructive() {
  if [[ "$SKIP_CONFIRM" == true || "$YES" == true ]]; then
    return 0
  fi

  echo
  warn "Будут остановлены сервисы AdminPanelAZ и удалены systemd units."
  if [[ "$REMOVE_NGINX" == true ]]; then
    warn "Будет удалена конфигурация nginx для панели."
  fi
  if [[ "$REMOVE_FIREWALL" == true ]]; then
    warn "Будут удалены правила firewall с меткой AdminPanelAZ."
  fi
  if [[ "$PURGE_STATE" == true ]]; then
    warn "Будут удалены каталоги состояния (/var/lib/adminpanelaz, /var/lib/adminpanelaz-node, .runtime)."
  fi
  if [[ "$REMOVE_ENV" == true ]]; then
    warn "Будут удалены backend/.env и backend/node_agent.env."
  fi
  if [[ "$REMOVE_SYSTEM_CONFIG" == true ]]; then
    warn "Будет удалён /etc/adminpanelaz (ddns.env, mtls, node_agent.env)."
  fi
  if [[ "$REMOVE_BACKUPS" == true ]]; then
    warn "Будет удалён каталог бэкапов панели."
  fi
  if [[ "$PURGE_REPO" == true ]]; then
    warn "Будет удалён каталог проекта: $ROOT_DIR"
  fi
  warn "Данные AntiZapret (/root/antizapret и др.) НЕ удаляются."
  echo
  echo "Для подтверждения введите yes или $PROJECT_NAME:"
  local answer=""
  read -r answer
  if [[ "$answer" == "yes" || "$answer" == "$PROJECT_NAME" ]]; then
    return 0
  fi
  die_confirm "Удаление отменено."
}

die_confirm() {
  echo "[uninstall] $*" >&2
  exit 1
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
  if [[ "$REMOVE_NGINX" != true ]]; then
    return 0
  fi

  local env_file="$ROOT_DIR/backend/.env"
  local domain=""

  if [[ -f "$env_file" ]]; then
    domain=$(grep -E '^DOMAIN=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '" ' || true)
  fi

  if [[ -z "$domain" ]]; then
    warn "DOMAIN не найден в backend/.env — пропуск удаления nginx (или укажите конфиг вручную)"
    return 0
  fi

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
  else
    log "Конфигурация nginx для $domain не найдена"
  fi

  if [[ -f /etc/ssl/certs/adminpanelaz.crt ]]; then
    rm -f /etc/ssl/certs/adminpanelaz.crt /etc/ssl/private/adminpanelaz.key
    log "Удалён самоподписанный сертификат adminpanelaz"
  fi
}

remove_firewall_rules() {
  if [[ "$REMOVE_FIREWALL" != true ]]; then
    return 0
  fi

  if [[ ! -f "$ROOT_DIR/scripts/firewall-setup.sh" ]]; then
    warn "scripts/firewall-setup.sh не найден — пропуск удаления firewall"
    return 0
  fi

  # shellcheck source=scripts/firewall-setup.sh
  source "$ROOT_DIR/scripts/firewall-setup.sh"
  firewall_remove_rules_from_env "$ROOT_DIR"
}

remove_system_config() {
  if [[ "$REMOVE_SYSTEM_CONFIG" != true ]]; then
    return 0
  fi

  local config_dir="/etc/adminpanelaz"
  if [[ -f "$config_dir/ddns.env" ]]; then
    rm -f "$config_dir/ddns.env"
    log "Удалён $config_dir/ddns.env"
  fi
  if [[ -d "$config_dir/mtls" ]]; then
    rm -rf "$config_dir/mtls"
    log "Удалён $config_dir/mtls"
  fi
  if [[ -f "$config_dir/node_agent.env" ]]; then
    rm -f "$config_dir/node_agent.env"
    log "Удалён $config_dir/node_agent.env"
  fi
  if [[ -d "$config_dir" ]] && [[ -z "$(ls -A "$config_dir" 2>/dev/null || true)" ]]; then
    rmdir "$config_dir" 2>/dev/null || true
  fi
}

remove_backup_dir() {
  if [[ "$REMOVE_BACKUPS" != true ]]; then
    return 0
  fi

  local env_file="$ROOT_DIR/backend/.env"
  local backup_root="/var/backups/adminpanelaz"
  if [[ -f "$env_file" ]]; then
    local custom
    custom=$(grep -E '^BACKUP_ROOT=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '" ' || true)
    if [[ -n "$custom" ]]; then
      backup_root="$custom"
    fi
  fi

  if [[ -d "$backup_root" ]]; then
    log "Удаление каталога бэкапов $backup_root..."
    rm -rf "$backup_root"
    log "Каталог бэкапов удалён"
  else
    log "Каталог бэкапов не найден: $backup_root"
  fi
}

remove_env_files() {
  if [[ "$REMOVE_ENV" != true ]]; then
    return 0
  fi

  local env_file="$ROOT_DIR/backend/.env"
  local node_env="$ROOT_DIR/backend/node_agent.env"
  if [[ -f "$env_file" ]]; then
    rm -f "$env_file"
    log "Удалён $env_file"
  fi
  if [[ -f "$node_env" ]]; then
    rm -f "$node_env"
    log "Удалён $node_env"
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

purge_repo_dir() {
  if [[ "$PURGE_REPO" != true ]]; then
    return 0
  fi

  if [[ ! -d "$ROOT_DIR" ]]; then
    warn "Каталог проекта уже отсутствует: $ROOT_DIR"
    return 0
  fi

  log "Удаление каталога проекта $ROOT_DIR..."
  rm -rf "$ROOT_DIR"
  log "Каталог проекта удалён"
}

print_summary() {
  if [[ "$PURGE_REPO" == true ]]; then
    log "Полное удаление завершено. Каталог проекта удалён."
    return
  fi

  log "Удаление завершено."
  if [[ "$PURGE_STATE" != true ]]; then
    warn "Каталоги состояния сохранены. Для удаления: sudo $0 --purge-state"
  fi
  if [[ "$REMOVE_ENV" != true ]]; then
    log "backend/.env и node_agent.env сохранены в $ROOT_DIR/backend/"
  fi
  log "Каталог проекта ($ROOT_DIR) сохранён."
  log "Данные AntiZapret не затронуты."
}

main() {
  parse_args "$@"

  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Запустите от root: sudo $0" >&2
    exit 1
  fi

  confirm_destructive

  stop_local_daemons
  remove_nginx_site_if_present
  remove_ddns_timer
  remove_systemd_unit "adminpanelaz"
  remove_systemd_unit "adminpanelaz-node"
  systemctl daemon-reload 2>/dev/null || true
  remove_firewall_rules
  remove_system_config

  if [[ "$PURGE_STATE" == true ]]; then
    purge_state_dirs
  fi

  remove_backup_dir
  remove_env_files

  # Каталог проекта удаляем последним (скрипт перестанет существовать)
  purge_repo_dir

  print_summary
}

main "$@"
