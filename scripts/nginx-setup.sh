#!/usr/bin/env bash
# Утилита публикации AdminPanelAZ: HTTP / Nginx / SSL (не установщик — первичная установка: ./install.sh)
# По образцу AdminAntizapret script_sh/ssl_setup.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/backend/.env}"
SERVICE_NAME="${SERVICE_NAME:-adminpanelaz}"
DEFAULT_PORT="${DEFAULT_PORT:-8000}"
HTTPS_PUBLIC_PORT="${HTTPS_PUBLIC_PORT:-443}"
HTTP_ACME_PORT="${HTTP_ACME_PORT:-80}"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

usage() {
  cat <<'EOF'
Использование: sudo ./scripts/nginx-setup.sh [команда]

Команды:
  (без аргументов)   Интерактивный мастер HTTP / Nginx / SSL
  --http             Только HTTP, uvicorn на 0.0.0.0 (без nginx)
  --nginx-le         Nginx + Let's Encrypt (нужен DOMAIN, опционально EMAIL)
  --nginx-selfsigned Nginx + самоподписанный сертификат
  --change           Сменить режим публикации (интерактивно)
  --help             Справка

Переменные окружения (для неинтерактивного режима):
  DOMAIN             Доменное имя
  EMAIL              Email для Let's Encrypt
  BACKEND_PORT       Порт uvicorn (по умолчанию 8000)
EOF
}

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    nginx_die "Запустите от root: sudo $0"
  fi
}

prompt_public_ports() {
  local https_default="${HTTPS_PUBLIC_PORT:-443}"
  local http_default="${HTTP_ACME_PORT:-80}"
  while true; do
    local reply=""
    read -r -p "Публичный HTTPS-порт Nginx (1-65535) [$https_default]: " reply
    reply="${reply:-$https_default}"
    if [[ "$reply" =~ ^[0-9]+$ ]] && ((reply >= 1 && reply <= 65535)) && [[ "$reply" != "$BACKEND_PORT" ]]; then
      HTTPS_PUBLIC_PORT="$reply"
      break
    fi
    echo "Некорректный порт или совпадает с backend."
  done
  while true; do
    local reply=""
    read -r -p "Публичный HTTP-порт (ACME/редирект) [$http_default]: " reply
    reply="${reply:-$http_default}"
    if [[ "$reply" =~ ^[0-9]+$ ]] && ((reply >= 1 && reply <= 65535)) \
      && [[ "$reply" != "$BACKEND_PORT" ]] && [[ "$reply" != "$HTTPS_PUBLIC_PORT" ]]; then
      HTTP_ACME_PORT="$reply"
      return 0
    fi
    echo "Некорректный порт или конфликт с другими портами."
  done
}

prompt_port() {
  local current
  current="$(nginx_env_get BACKEND_PORT)"
  current="${current:-$DEFAULT_PORT}"
  while true; do
    local reply=""
    read -r -p "Порт uvicorn (1-65535) [$current]: " reply
    reply="${reply:-$current}"
    if [[ "$reply" =~ ^[0-9]+$ ]] && ((reply >= 1 && reply <= 65535)); then
      BACKEND_PORT="$reply"
      return 0
    fi
    echo "Некорректный порт."
  done
}

prompt_domain() {
  while true; do
    read -r -p "Доменное имя (например, panel.example.com): " DOMAIN
    if [[ "$DOMAIN" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
      return 0
    fi
    echo "Неверный формат домена."
  done
}

restart_panel_if_needed() {
  if systemctl is-enabled "$SERVICE_NAME" >/dev/null 2>&1; then
    systemctl restart "$SERVICE_NAME" 2>/dev/null || nginx_warn "Не удалось перезапустить $SERVICE_NAME"
  elif [[ -x "$ROOT_DIR/start.sh" ]]; then
    "$ROOT_DIR/start.sh" restart 2>/dev/null || nginx_warn "Перезапустите панель вручную: ./start.sh restart"
  fi
}

setup_http_direct() {
  prompt_port
  nginx_apply_direct_http_env "$BACKEND_PORT"
  nginx_remove_site "$(nginx_env_get DOMAIN)"
  nginx_log "HTTP без nginx: http://<сервер>:${BACKEND_PORT}/"
  restart_panel_if_needed
}

setup_nginx_letsencrypt() {
  local domain="${DOMAIN:-}"
  local email="${EMAIL:-}"
  if [[ -z "$domain" ]]; then
    prompt_domain
    domain="$DOMAIN"
  fi
  if [[ -z "${email:-}" ]] && [[ -t 0 ]]; then
    read -r -p "Email для Let's Encrypt (ENTER — пропустить): " email
  fi
  prompt_port
  prompt_public_ports

  nginx_ensure_nginx || nginx_die "Не удалось установить nginx"
  nginx_obtain_letsencrypt_cert "$domain" "$email"

  local cert="/etc/letsencrypt/live/${domain}/fullchain.pem"
  local key="/etc/letsencrypt/live/${domain}/privkey.pem"
  local conf
  conf="$(nginx_render_template \
    "$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template" \
    "$domain" "$BACKEND_PORT" "$cert" "$key" "$HTTPS_PUBLIC_PORT" "$HTTP_ACME_PORT")"
  nginx_install_site "$conf" "$domain"
  nginx_apply_behind_proxy_env "$domain" "$BACKEND_PORT" "https"

  systemctl enable --now snap.certbot.renew.timer 2>/dev/null || \
    systemctl enable --now certbot.timer 2>/dev/null || true

  nginx_log "Nginx + Let's Encrypt настроен: https://${domain}/"
  restart_panel_if_needed
}

setup_nginx_selfsigned() {
  local domain="${DOMAIN:-}"
  if [[ -z "$domain" ]]; then
    if [[ -t 0 ]]; then
      read -r -p "Домен для server_name (ENTER — $(hostname -f 2>/dev/null || hostname)): " domain
    fi
    domain="${domain:-$(hostname -f 2>/dev/null || hostname)}"
  fi
  prompt_port
  prompt_public_ports
  nginx_ensure_nginx || nginx_die "Не удалось установить nginx"

  mkdir -p /etc/ssl/private
  if [[ ! -f "$NGINX_SELF_SIGNED_CERT" ]]; then
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout "$NGINX_SELF_SIGNED_KEY" \
      -out "$NGINX_SELF_SIGNED_CERT" \
      -subj "/CN=${domain}" >/dev/null 2>&1
  fi

  local conf
  conf="$(nginx_render_template \
    "$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template" \
    "$domain" "$BACKEND_PORT" "$NGINX_SELF_SIGNED_CERT" "$NGINX_SELF_SIGNED_KEY" \
    "$HTTPS_PUBLIC_PORT" "$HTTP_ACME_PORT")"
  nginx_install_site "$conf" "$domain"
  nginx_apply_behind_proxy_env "$domain" "$BACKEND_PORT" "https"
  nginx_log "Nginx + самоподписанный SSL: https://${domain}/"
  restart_panel_if_needed
}

setup_nginx_custom_certs() {
  local domain="${DOMAIN:-}"
  local cert_path="${SSL_CERT:-}"
  local key_path="${SSL_KEY:-}"

  if [[ -z "$domain" ]]; then
    prompt_domain
    domain="$DOMAIN"
  fi
  if [[ -z "$cert_path" ]]; then
    read -r -p "Путь к сертификату (.crt/.pem): " cert_path
  fi
  if [[ -z "$key_path" ]]; then
    read -r -p "Путь к приватному ключу (.key): " key_path
  fi
  [[ -f "$cert_path" && -f "$key_path" ]] || nginx_die "Файлы сертификата не найдены"
  prompt_port
  prompt_public_ports
  nginx_ensure_nginx || nginx_die "Не удалось установить nginx"

  local conf
  conf="$(nginx_render_template \
    "$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template" \
    "$domain" "$BACKEND_PORT" "$cert_path" "$key_path" \
    "$HTTPS_PUBLIC_PORT" "$HTTP_ACME_PORT")"
  nginx_install_site "$conf" "$domain"
  nginx_apply_behind_proxy_env "$domain" "$BACKEND_PORT" "https"
  nginx_log "Nginx + пользовательские сертификаты: https://${domain}/"
  restart_panel_if_needed
}

choose_installation_type() {
  echo
  echo "Выберите способ публикации AdminPanelAZ:"
  echo "  1) HTTPS — Nginx reverse proxy + Let's Encrypt (рекомендуется)"
  echo "  2) HTTPS — Nginx + самоподписанный сертификат"
  echo "  3) HTTPS — Nginx + собственные сертификаты"
  echo "  4) HTTP — uvicorn напрямую без nginx (только LAN / тесты, не для интернета)"
  read -r -p "Ваш выбор [1-4]: " choice
  case "$choice" in
    1) setup_nginx_letsencrypt ;;
    2) setup_nginx_selfsigned ;;
    3) setup_nginx_custom_certs ;;
    4) setup_http_direct ;;
    *) nginx_die "Неверный выбор" ;;
  esac
}

main() {
  require_root
  mkdir -p "$(dirname "$ENV_FILE")"
  touch "$ENV_FILE"

  case "${1:-}" in
    --http)
      BACKEND_PORT="${BACKEND_PORT:-$(nginx_env_get BACKEND_PORT)}"
      BACKEND_PORT="${BACKEND_PORT:-$DEFAULT_PORT}"
      setup_http_direct
      ;;
    --nginx-le)
      setup_nginx_letsencrypt
      ;;
    --nginx-selfsigned)
      setup_nginx_selfsigned
      ;;
    --change|"")
      choose_installation_type
      ;;
    --help|-h)
      usage
      ;;
    *)
      usage
      nginx_die "Неизвестный аргумент: $1"
      ;;
  esac

  cat <<EOF

Готово. Проверка:
  nginx -t
  systemctl status nginx
  systemctl status ${SERVICE_NAME}
  curl -kI https://\${DOMAIN:-127.0.0.1}/api/health

Конфигурация backend: ${ENV_FILE}
EOF
}

main "$@"
