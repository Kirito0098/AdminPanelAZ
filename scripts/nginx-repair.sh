#!/usr/bin/env bash
# Восстановление nginx для AdminPanelAZ после сбоя сторонних скриптов
# (например uninstall StatusOpenVPN, который ломает или оставляет мёртвый vhost).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/backend/.env}"
SERVICE_NAME="${SERVICE_NAME:-adminpanelaz}"
NON_INTERACTIVE="${NON_INTERACTIVE:-false}"
SKIP_PANEL_RESTART="${SKIP_PANEL_RESTART:-false}"
DOMAIN_OVERRIDE="${DOMAIN:-}"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

usage() {
  cat <<'EOF'
Использование: sudo ./scripts/nginx-repair.sh [опции]

Восстанавливает выделенный nginx vhost AdminPanelAZ по настройкам backend/.env.
Удаляет сломанные/чужие vhost'ы домена (в т.ч. остатки StatusOpenVPN) и snippet-include.

Опции:
  --non-interactive   Не спрашивать домен (нужен DOMAIN в .env или переменная DOMAIN=)
  --no-panel-restart  Не перезапускать adminpanelaz после применения
  --help              Справка

Переменные окружения:
  DOMAIN              Переопределить домен из .env
  ENV_FILE            Путь к .env (по умолчанию backend/.env)
  SKIP_PANEL_RESTART  true — не перезапускать панель

Пример:
  sudo ./scripts/nginx-repair.sh
  sudo DOMAIN=panel.example.com ./scripts/nginx-repair.sh --non-interactive
EOF
}

is_non_interactive() {
  [[ "$NON_INTERACTIVE" == "true" || "$NON_INTERACTIVE" == "1" ]] || [[ ! -t 0 ]]
}

require_root() {
  [[ "$(id -u)" -eq 0 ]] || nginx_die "Запустите от root: sudo $0"
}

validate_domain() {
  local value="$1"
  [[ "$value" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]] || nginx_die "Неверный формат домена: $value"
}

validate_port() {
  local value="$1"
  local label="$2"
  [[ "$value" =~ ^[0-9]+$ ]] && ((value >= 1 && value <= 65535)) || nginx_die "${label}: некорректный порт (1-65535)"
}

restart_panel_if_needed() {
  if [[ "$SKIP_PANEL_RESTART" == "true" || "$SKIP_PANEL_RESTART" == "1" ]]; then
    nginx_log "Перезапуск панели пропущен (SKIP_PANEL_RESTART)"
    return 0
  fi
  if systemctl is-enabled "$SERVICE_NAME" >/dev/null 2>&1; then
    systemctl restart "$SERVICE_NAME" 2>/dev/null || nginx_warn "Не удалось перезапустить $SERVICE_NAME"
  elif [[ -x "$ROOT_DIR/start.sh" ]]; then
    "$ROOT_DIR/start.sh" restart 2>/dev/null || nginx_warn "Перезапустите панель вручную: ./start.sh restart"
  fi
}

load_panel_publish_settings() {
  BACKEND_PORT="$(nginx_env_get BACKEND_PORT)"
  BACKEND_PORT="${BACKEND_PORT:-8000}"
  HTTPS_PUBLIC_PORT="$(nginx_env_get HTTPS_PUBLIC_PORT)"
  HTTP_ACME_PORT="$(nginx_env_get HTTP_ACME_PORT)"
  HTTPS_PUBLIC_PORT="${HTTPS_PUBLIC_PORT:-443}"
  HTTP_ACME_PORT="${HTTP_ACME_PORT:-80}"
  ACCESS_PATH="$(nginx_env_get ACCESS_PATH)"
  PUBLISH_MODE="$(nginx_env_get PUBLISH_MODE)"

  if [[ -n "$DOMAIN_OVERRIDE" ]]; then
    DOMAIN="$DOMAIN_OVERRIDE"
  else
    DOMAIN="$(nginx_env_get DOMAIN)"
  fi

  validate_port "$BACKEND_PORT" "BACKEND_PORT"
  validate_port "$HTTPS_PUBLIC_PORT" "HTTPS_PUBLIC_PORT"
  validate_port "$HTTP_ACME_PORT" "HTTP_ACME_PORT"
  [[ "$HTTPS_PUBLIC_PORT" != "$BACKEND_PORT" ]] || nginx_die "HTTPS_PUBLIC_PORT совпадает с BACKEND_PORT"
}

prompt_domain_if_needed() {
  if [[ -n "$DOMAIN" ]]; then
    return 0
  fi
  if is_non_interactive; then
    nginx_die "DOMAIN не задан в ${ENV_FILE}. Укажите домен или запустите без --non-interactive."
  fi
  while true; do
    read -r -p "Домен панели (например, panel.example.com): " DOMAIN
    if [[ "$DOMAIN" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
      return 0
    fi
    echo "Неверный формат домена."
  done
}

print_access_url() {
  local path_suffix
  path_suffix="$(nginx_access_path_suffix "$(nginx_normalize_access_path "${ACCESS_PATH:-}")")"
  if [[ "$HTTPS_PUBLIC_PORT" == "443" ]]; then
    nginx_log "Панель: https://${DOMAIN}${path_suffix}"
  else
    nginx_log "Панель: https://${DOMAIN}:${HTTPS_PUBLIC_PORT}${path_suffix}"
  fi
}

verify_panel_health() {
  local path_prefix health_path code host_header
  path_prefix="$(nginx_normalize_access_path "${ACCESS_PATH:-}")"
  health_path="${path_prefix}/api/health"
  host_header="$DOMAIN"
  if [[ "$HTTPS_PUBLIC_PORT" == "443" ]]; then
    code="$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: ${host_header}" "https://127.0.0.1${health_path}" 2>/dev/null || echo "000")"
  else
    code="$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: ${host_header}" "https://127.0.0.1:${HTTPS_PUBLIC_PORT}${health_path}" 2>/dev/null || echo "000")"
  fi
  if [[ "$code" == "200" ]]; then
    nginx_log "Проверка через nginx: OK (HTTP ${code}${health_path})"
    return 0
  fi
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${BACKEND_PORT}${health_path}" 2>/dev/null || echo "000")"
  if [[ "$code" == "200" ]]; then
    nginx_log "Проверка uvicorn: OK (HTTP ${code} на 127.0.0.1:${BACKEND_PORT}${health_path})"
    return 0
  fi
  nginx_warn "Health-check не прошёл (nginx/uvicorn: HTTP ${code}) — проверьте: systemctl status ${SERVICE_NAME}"
  return 0
}

repair_nginx_for_panel() {
  local domain="$1"

  nginx_log "Домен: ${domain}"
  nginx_log "Порт приложения: ${BACKEND_PORT}"
  if [[ -n "$(nginx_normalize_access_path "${ACCESS_PATH:-}")" ]]; then
    nginx_log "Подпуть ACCESS_PATH: $(nginx_normalize_access_path "${ACCESS_PATH:-}")"
  else
    nginx_log "Подпуть ACCESS_PATH: корень домена"
  fi

  nginx_ensure_nginx || nginx_die "Не удалось установить nginx"

  nginx_cleanup_subpath_snippets_for_domain "$domain"
  nginx_remove_all_vhosts_for_domain "$domain"
  nginx_remove_our_dedicated_sites_for_domain "$domain"

  nginx_resolve_panel_ssl_cert_paths "$domain" || nginx_die \
    "Не найден SSL-сертификат для ${domain}. Проверьте Let's Encrypt (/etc/letsencrypt/live/${domain}/) или SSL_CERT/SSL_KEY в ${ENV_FILE}"

  ACCESS_PATH="$(nginx_normalize_access_path "${ACCESS_PATH:-}")"
  export ACCESS_PATH

  nginx_log "Установка выделенного vhost AdminPanelAZ…"
  nginx_install_dedicated_panel_vhost \
    "$domain" "$BACKEND_PORT" "$NGINX_SSL_CERT" "$NGINX_SSL_KEY" \
    "$HTTPS_PUBLIC_PORT" "$HTTP_ACME_PORT"

  nginx_apply_behind_proxy_env "$domain" "$BACKEND_PORT" "https" "$HTTPS_PUBLIC_PORT" "$HTTP_ACME_PORT"

  case "${PUBLISH_MODE:-}" in
    nginx_le|nginx_selfsigned|nginx_custom|"") nginx_set_publish_mode "${PUBLISH_MODE:-nginx_le}" ;;
    *) nginx_warn "PUBLISH_MODE=${PUBLISH_MODE} — .env обновлён только для nginx reverse proxy" ;;
  esac

  nginx_log "Nginx восстановлен."
  print_access_url
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive) NON_INTERACTIVE=true ;;
    --no-panel-restart) SKIP_PANEL_RESTART=true ;;
    --help|-h) usage; exit 0 ;;
    *) nginx_die "Неизвестный аргумент: $1 (см. --help)" ;;
  esac
  shift
done

require_root
[[ -f "$ENV_FILE" ]] || nginx_die "Не найден файл настроек: ${ENV_FILE}"

nginx_log "Восстановление nginx для AdminPanelAZ"
nginx_log "Настройки: ${ENV_FILE}"

load_panel_publish_settings
prompt_domain_if_needed
validate_domain "$DOMAIN"

repair_nginx_for_panel "$DOMAIN"
restart_panel_if_needed
verify_panel_health

nginx_log "Готово. Бэкапы старых конфигов: /etc/nginx/backups/"
