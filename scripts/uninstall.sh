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
KEEP_AGENT_PKI=false
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
  --purge-state         Удалить каталоги состояния (/var/lib/adminpanelaz*, .runtime)
  --purge               Удалить каталог проекта ($ROOT_DIR) — необратимо
  --remove-nginx        Удалить конфигурацию nginx сайта (по DOMAIN из backend/.env)
  --remove-firewall     Удалить правила firewall AdminPanelAZ (ufw и iptables)
  --remove-env          Удалить backend/.env, node_agent.env и proxy_agent.env
  --remove-backups      Удалить каталог бэкапов (BACKUP_ROOT из backend/.env)
  --remove-system-config  Удалить /etc/adminpanelaz (ddns.env, mtls, node_agent.env)
  --keep-agent-pki        С --remove-system-config: оставить /etc/adminpanelaz/mtls (переустановка)
  -y, --yes             Без интерактивных подтверждений
  --skip-confirm        Не спрашивать подтверждение (вызывается из install.sh после своего диалога)
  --help                Показать справку

По умолчанию останавливает сервисы и удаляет systemd units (adminpanelaz, adminpanelaz-node, adminpanelaz-proxy, DDNS timer).
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
      --keep-agent-pki)
        KEEP_AGENT_PKI=true
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
    warn "Будут удалены каталоги состояния (/var/lib/adminpanelaz, /var/lib/adminpanelaz-node, /var/lib/adminpanelaz-proxy, .runtime)."
  fi
  if [[ "$REMOVE_ENV" == true ]]; then
    warn "Будут удалены backend/.env, node_agent.env и proxy_agent.env."
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

systemd_unit_exists() {
  local name="$1"
  systemctl cat "$name" >/dev/null 2>&1 \
    || [[ -f "/etc/systemd/system/${name}" ]] \
    || [[ -f "/etc/systemd/system/${name}.service" ]]
}

stop_systemd_unit_if_loaded() {
  local name="$1"

  if ! systemd_unit_exists "$name"; then
    return 0
  fi

  log "Остановка systemd unit $name..."
  systemctl stop "$name" 2>/dev/null || true
  systemctl disable "$name" 2>/dev/null || true
  systemctl reset-failed "$name" 2>/dev/null || true
}

remove_systemd_unit() {
  local name="$1"
  local unit="/etc/systemd/system/${name}.service"

  stop_systemd_unit_if_loaded "$name"

  if [[ ! -f "$unit" ]]; then
    return 0
  fi

  rm -f "$unit"
  log "Удалён $unit"
}

remove_ddns_timer() {
  local timer="adminpanelaz-ddns.timer"
  local service="adminpanelaz-ddns.service"

  if [[ ! -f "/etc/systemd/system/$timer" \
    && ! -f "/etc/systemd/system/$service" ]] \
    && ! systemctl is-enabled "$timer" >/dev/null 2>&1 \
    && ! systemctl is-enabled "$service" >/dev/null 2>&1; then
    return 0
  fi

  log "Удаление DDNS timer..."
  if [[ -x "$ROOT_DIR/scripts/ddns-update.sh" ]]; then
    "$ROOT_DIR/scripts/ddns-update.sh" remove-timer 2>/dev/null || true
  else
    stop_systemd_unit_if_loaded "$timer"
    stop_systemd_unit_if_loaded "$service"
    rm -f "/etc/systemd/system/$timer" "/etc/systemd/system/$service"
    systemctl daemon-reload 2>/dev/null || true
  fi
  log "DDNS timer удалён"
}

stop_all_services() {
  log "Остановка всех сервисов AdminPanelAZ..."
  stop_systemd_unit_if_loaded "adminpanelaz-ddns.timer"
  stop_systemd_unit_if_loaded "adminpanelaz-ddns.service"
  stop_systemd_unit_if_loaded "adminpanelaz"
  stop_systemd_unit_if_loaded "adminpanelaz-node"
  stop_systemd_unit_if_loaded "adminpanelaz-proxy"
}

# nginx_conf_users <каталог nginx> <ERE> [файл, который не считается]: файлы, где ERE стоит вне комментария.
nginx_conf_users() {
  local dir="$1" pattern="$2" skip="${3:-}" path
  while IFS= read -r path; do
    [[ -n "$skip" && "$path" == "$skip" ]] && continue
    sed 's/#.*//' "$path" 2>/dev/null | grep -Eq -- "$pattern" && printf '%s\n' "$path"
  done < <(find "$dir" -path "$dir/backups" -prune -o \( -type f -o -type l \) -print 2>/dev/null | sort)
  return 0
}

# Snippets Cloudflare подключают и vhost портала, и vhost других доменов панели, и чужие сайты:
# удалить подключённый snippet — nginx не поднимется при следующем перезапуске.
remove_nginx_shared_file_unless_used() {
  local file="$1" label="$2"
  shift 2
  [[ -f "$file" ]] || return 0
  if [[ -n "$*" ]]; then
    warn "${label} ${file} оставлен, его использует: $*"
    return 0
  fi
  rm -f "$file"
  log "Удалён ${label}: ${file}"
  NGINX_CHANGED=true
}

remove_nginx_site_if_present() {
  if [[ "$REMOVE_NGINX" != true ]]; then
    return 0
  fi

  local env_file="$ROOT_DIR/backend/.env"
  local domain=""
  local nginx_dir="${NGINX_DIR:-/etc/nginx}"
  local ssl_dir="${SSL_DIR:-/etc/ssl}"

  if [[ -f "$env_file" ]]; then
    domain=$(grep -E '^DOMAIN=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '" ' || true)
  fi

  if [[ -z "$domain" ]]; then
    warn "DOMAIN не найден в backend/.env — пропуск удаления nginx (или укажите конфиг вручную)"
    return 0
  fi

  local conf_base="${domain//./_}"
  local removed=false
  NGINX_CHANGED=false
  for path in "${nginx_dir}/sites-available/${conf_base}" "${nginx_dir}/sites-enabled/${conf_base}" \
    "${nginx_dir}/sites-available/00-adminpanelaz-default-deny" "${nginx_dir}/sites-enabled/00-adminpanelaz-default-deny"; do
    if [[ -f "$path" || -L "$path" ]]; then
      rm -f "$path"
      removed=true
    fi
  done

  if [[ "$removed" == true ]]; then
    log "Удалена конфигурация nginx для $domain"
    NGINX_CHANGED=true
  else
    log "Конфигурация nginx для $domain не найдена"
  fi

  if [[ -f "${ssl_dir}/certs/adminpanelaz.crt" ]]; then
    rm -f "${ssl_dir}/certs/adminpanelaz.crt" "${ssl_dir}/private/adminpanelaz.key"
    log "Удалён самоподписанный сертификат adminpanelaz"
  fi
  rm -f "${ssl_dir}/certs/adminpanelaz-default-deny.crt" "${ssl_dir}/private/adminpanelaz-default-deny.key"

  local realip="${nginx_dir}/snippets/cloudflare-realip.conf"
  local allow="${nginx_dir}/snippets/cloudflare-origin-allow.conf"
  local lock="${nginx_dir}/snippets/cloudflare-origin-lock.conf"
  local geo="${nginx_dir}/conf.d/adminpanelaz-cloudflare-origin.conf"
  local -a users=()

  mapfile -t users < <(nginx_conf_users "$nginx_dir" 'include[[:space:]]+[^;]*cloudflare-realip\.conf')
  remove_nginx_shared_file_unless_used "$realip" "snippet Cloudflare realip" "${users[@]}"

  mapfile -t users < <(nginx_conf_users "$nginx_dir" 'include[[:space:]]+[^;]*cloudflare-origin-lock\.conf')
  remove_nginx_shared_file_unless_used "$lock" "snippet Cloudflare origin lock" "${users[@]}"

  # geo задаёт $adminpanelaz_cf_origin для origin lock; allow — его источник при обновлении списков.
  # shellcheck disable=SC2016
  mapfile -t users < <(nginx_conf_users "$nginx_dir" '\$adminpanelaz_cf_origin([^_[:alnum:]]|$)' "$geo")
  remove_nginx_shared_file_unless_used "$geo" "Cloudflare origin geo" "${users[@]}"
  if [[ ! -f "$geo" ]]; then
    remove_nginx_shared_file_unless_used "$allow" "snippet Cloudflare origin allow"
  fi

  if [[ "$NGINX_CHANGED" == true ]] && command -v nginx >/dev/null 2>&1; then
    if ! nginx -t >/dev/null 2>&1; then
      warn "nginx -t не прошёл после удаления — nginx не перезагружен, проверьте: nginx -t"
    elif ! systemctl reload nginx 2>/dev/null; then
      warn "nginx не перезагружен"
    fi
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

  local config_dir="${ADMINPANELAZ_CONFIG_DIR:-/etc/adminpanelaz}"
  if [[ -f "$config_dir/ddns.env" ]]; then
    rm -f "$config_dir/ddns.env"
    log "Удалён $config_dir/ddns.env"
  fi
  if [[ "$KEEP_AGENT_PKI" == true ]]; then
    log "Сохранён $config_dir/mtls: панель уже доверяет этим сертификатам агента"
  elif [[ -d "$config_dir/mtls" ]]; then
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
  local proxy_env="$ROOT_DIR/backend/proxy_agent.env"
  if [[ -f "$env_file" ]]; then
    rm -f "$env_file"
    log "Удалён $env_file"
  fi
  if [[ -f "$node_env" ]]; then
    rm -f "$node_env"
    log "Удалён $node_env"
  fi
  if [[ -f "$proxy_env" ]]; then
    rm -f "$proxy_env"
    log "Удалён $proxy_env"
  fi
}

purge_state_dirs() {
  local dirs=(
    /var/lib/adminpanelaz
    /var/lib/adminpanelaz-node
    /var/lib/adminpanelaz-proxy
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
    log "backend/.env, node_agent.env и proxy_agent.env сохранены в $ROOT_DIR/backend/"
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

  stop_all_services
  remove_nginx_site_if_present
  remove_ddns_timer
  remove_systemd_unit "adminpanelaz"
  remove_systemd_unit "adminpanelaz-node"
  remove_systemd_unit "adminpanelaz-proxy"
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
