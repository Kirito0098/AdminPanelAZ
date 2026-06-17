#!/usr/bin/env bash
# Общие функции для настройки Nginx (AdminPanelAZ, по образцу AdminAntizapret ssl_setup.sh)

nginx_common_init() {
  : "${ROOT_DIR:?ROOT_DIR не задан}"
  : "${ENV_FILE:?ENV_FILE не задан}"
  NGINX_TEMPLATE_DIR="${ROOT_DIR}/deploy/nginx"
  NGINX_SELF_SIGNED_CERT="/etc/ssl/certs/adminpanelaz.crt"
  NGINX_SELF_SIGNED_KEY="/etc/ssl/private/adminpanelaz.key"
}

nginx_log() {
  echo "[nginx-setup] $*"
}

nginx_warn() {
  echo "[nginx-setup] ВНИМАНИЕ: $*" >&2
}

nginx_die() {
  echo "[nginx-setup] ОШИБКА: $*" >&2
  exit 1
}

nginx_env_get() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true
}

nginx_env_set() {
  local key="$1"
  local value="$2"
  local escaped
  mkdir -p "$(dirname "$ENV_FILE")"
  touch "$ENV_FILE"
  escaped=$(printf '%s' "$value" | sed 's/[&|]/\\&/g')
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
  fi
}

nginx_env_unset() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 0
  sed -i "/^${key}=/d" "$ENV_FILE"
}

nginx_conf_basename() {
  local domain="$1"
  printf '%s\n' "${domain//./_}"
}

nginx_conf_paths() {
  local domain="$1"
  local base
  base="$(nginx_conf_basename "$domain")"
  NGINX_CONF_FILE="/etc/nginx/sites-available/${base}"
  NGINX_ENABLED_LINK="/etc/nginx/sites-enabled/${base}"
}

nginx_ensure_certbot() {
  if command -v certbot >/dev/null 2>&1; then
    return 0
  fi
  if command -v snap >/dev/null 2>&1; then
    snap install core >/dev/null 2>&1 || snap refresh core >/dev/null 2>&1 || true
    snap install --classic certbot >/dev/null 2>&1 || snap refresh certbot >/dev/null 2>&1 || true
    ln -sf /snap/bin/certbot /usr/bin/certbot >/dev/null 2>&1 || true
  fi
  if ! command -v certbot >/dev/null 2>&1; then
    apt-get install -y -qq certbot --no-install-recommends >/dev/null 2>&1 || return 1
  fi
  command -v certbot >/dev/null 2>&1
}

nginx_ensure_nginx() {
  if command -v nginx >/dev/null 2>&1; then
    return 0
  fi
  apt-get update -qq
  apt-get install -y -qq nginx >/dev/null 2>&1
}

nginx_https_redirect_suffix() {
  local https_port="${1:-443}"
  if [[ "$https_port" == "443" ]]; then
    printf ''
  else
    printf ':%s' "$https_port"
  fi
}

nginx_public_origin_host() {
  local domain="$1"
  local https_port="${2:-443}"
  printf '%s%s' "$domain" "$(nginx_https_redirect_suffix "$https_port")"
}

nginx_render_template() {
  local template="$1"
  local domain="$2"
  local backend_port="$3"
  local ssl_cert="${4:-}"
  local ssl_key="${5:-}"
  local https_port="${6:-443}"
  local http_port="${7:-80}"
  local https_redirect_suffix
  https_redirect_suffix="$(nginx_https_redirect_suffix "$https_port")"
  sed \
    -e "s|__DOMAIN__|${domain}|g" \
    -e "s|__BACKEND_PORT__|${backend_port}|g" \
    -e "s|__HTTPS_PORT__|${https_port}|g" \
    -e "s|__HTTPS_REDIRECT_SUFFIX__|${https_redirect_suffix}|g" \
    -e "s|__HTTP_PORT__|${http_port}|g" \
    -e "s|__SSL_CERT__|${ssl_cert}|g" \
    -e "s|__SSL_KEY__|${ssl_key}|g" \
    "$template"
}

nginx_update_cors_for_domain() {
  local domain="$1"
  local scheme="${2:-https}"
  local https_public_port="${3:-$(nginx_env_get HTTPS_PUBLIC_PORT)}"
  https_public_port="${https_public_port:-443}"
  local public_host
  public_host="$(nginx_public_origin_host "$domain" "$https_public_port")"
  local backend_port
  backend_port="$(nginx_env_get BACKEND_PORT)"
  backend_port="${backend_port:-8000}"
  local origins="http://127.0.0.1:${backend_port},http://localhost:${backend_port}"
  origins+=",${scheme}://${public_host}"
  if [[ "$scheme" == "https" ]]; then
    origins+=",http://${public_host}"
  fi
  origins+=",http://127.0.0.1:5173,http://localhost:5173"
  nginx_env_set CORS_ORIGINS "$origins"
}

nginx_apply_behind_proxy_env() {
  local domain="$1"
  local backend_port="$2"
  local scheme="${3:-https}"
  local https_public_port="${4:-${HTTPS_PUBLIC_PORT:-443}}"
  local http_acme_port="${5:-${HTTP_ACME_PORT:-80}}"

  nginx_env_set BACKEND_HOST "127.0.0.1"
  nginx_env_set BACKEND_PORT "$backend_port"
  nginx_env_set DOMAIN "$domain"
  nginx_env_set BEHIND_NGINX "true"
  nginx_env_set HTTPS_PUBLIC_PORT "$https_public_port"
  nginx_env_set HTTP_ACME_PORT "$http_acme_port"
  nginx_env_set TRUSTED_PROXY_IPS "127.0.0.1,::1"
  nginx_env_set FORWARDED_ALLOW_IPS "127.0.0.1,::1"
  nginx_update_cors_for_domain "$domain" "$scheme" "$https_public_port"
}

nginx_apply_direct_http_env() {
  local backend_port="$1"
  nginx_env_set BACKEND_HOST "0.0.0.0"
  nginx_env_set BACKEND_PORT "$backend_port"
  nginx_env_unset DOMAIN
  nginx_env_set BEHIND_NGINX "false"
  nginx_env_unset TRUSTED_PROXY_IPS
  nginx_env_unset FORWARDED_ALLOW_IPS
}

nginx_install_site() {
  local conf_content="$1"
  local domain="$2"

  nginx_conf_paths "$domain"
  printf '%s\n' "$conf_content" >"$NGINX_CONF_FILE"
  ln -sf "$NGINX_CONF_FILE" "$NGINX_ENABLED_LINK"
  rm -f /etc/nginx/sites-enabled/default
  nginx -t || nginx_die "nginx -t не прошёл (конфиг: $NGINX_CONF_FILE)"
  systemctl enable nginx >/dev/null 2>&1 || true
  systemctl restart nginx || nginx_die "Не удалось запустить nginx"
}

nginx_update_proxy_port() {
  local new_port="$1"
  local domain
  domain="$(nginx_env_get DOMAIN)"
  [ -n "$domain" ] || return 0
  nginx_conf_paths "$domain"
  [ -f "$NGINX_CONF_FILE" ] || return 0
  if grep -q "proxy_pass http://127.0.0.1:" "$NGINX_CONF_FILE"; then
    sed -i -E "s|proxy_pass http://127.0.0.1:[0-9]+;|proxy_pass http://127.0.0.1:${new_port};|" "$NGINX_CONF_FILE"
    nginx -t >/dev/null 2>&1 && systemctl reload nginx 2>/dev/null && \
      nginx_log "Nginx proxy_pass обновлён на порт $new_port" || \
      nginx_warn "Порт в .env изменён, но nginx не перезагружен — проверьте $NGINX_CONF_FILE"
  fi
}

nginx_temp_clear_port80_nat() {
  SAVE_RULES=""
  PORT80_RULES=""
  if ! command -v iptables-save >/dev/null 2>&1; then
    return 0
  fi
  SAVE_RULES=$(iptables-save)
  local iface
  iface=$(ip route 2>/dev/null | awk '/default/ {print $5; exit}')
  [ -n "$iface" ] || return 0
  PORT80_RULES=$(iptables-save | grep "PREROUTING.*-p tcp.*--dport 80" | grep "$iface" || true)
  if [ -n "$PORT80_RULES" ]; then
    local -a rule_parts=()
    while read -r line; do
      [ -n "$line" ] || continue
      read -r -a rule_parts <<<"${line#-A }"
      iptables -t nat -D "${rule_parts[@]}" 2>/dev/null || true
    done <<<"$PORT80_RULES"
    nginx_log "Временно сняты iptables-правила NAT для порта 80"
  fi
}

nginx_restore_port80_nat() {
  if [ -n "${SAVE_RULES:-}" ]; then
    echo "$SAVE_RULES" | iptables-restore 2>/dev/null || true
  fi
}

nginx_obtain_letsencrypt_cert() {
  local domain="$1"
  local email="$2"
  local cert_path="/etc/letsencrypt/live/${domain}/fullchain.pem"

  if [ -f "$cert_path" ]; then
    nginx_log "Сертификат Let's Encrypt для $domain уже существует"
    return 0
  fi

  nginx_ensure_certbot || nginx_die "Не удалось установить certbot"
  systemctl stop nginx 2>/dev/null || true
  nginx_temp_clear_port80_nat

  if [[ -n "$email" ]]; then
    certbot certonly --standalone --non-interactive --agree-tos -m "$email" -d "$domain" || {
      nginx_restore_port80_nat
      systemctl start nginx 2>/dev/null || true
      if [[ "${NGINX_FAIL_SOFT:-false}" == true ]]; then
        nginx_warn "Не удалось получить сертификат Let's Encrypt"
        return 1
      fi
      nginx_die "Не удалось получить сертификат Let's Encrypt"
    }
  else
    certbot certonly --standalone --non-interactive --agree-tos --register-unsafely-without-email -d "$domain" || {
      nginx_restore_port80_nat
      systemctl start nginx 2>/dev/null || true
      if [[ "${NGINX_FAIL_SOFT:-false}" == true ]]; then
        nginx_warn "Не удалось получить сертификат Let's Encrypt"
        return 1
      fi
      nginx_die "Не удалось получить сертификат Let's Encrypt"
    }
  fi

  nginx_restore_port80_nat
  [ -f "$cert_path" ] || nginx_die "Сертификат не найден после certbot: $cert_path"
}

nginx_remove_site() {
  local domain="$1"
  [ -n "$domain" ] || return 0
  nginx_conf_paths "$domain"
  rm -f "$NGINX_CONF_FILE" "$NGINX_ENABLED_LINK"
  if command -v nginx >/dev/null 2>&1; then
    nginx -t >/dev/null 2>&1 && systemctl reload nginx 2>/dev/null || true
  fi
}
