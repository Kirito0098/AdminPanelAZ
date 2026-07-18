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

# Первый IPv4 сервера (для CN самоподписанного cert, если домен не задан).
nginx_server_primary_ip() {
  local ip=""
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$ip"
    return 0
  fi
  if command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
    if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "$ip"
      return 0
    fi
  fi
  return 1
}

# CN для самоподписанного сертификата: домен из аргумента/DOMAIN или IP сервера.
nginx_resolve_selfsigned_cn() {
  local domain="${1:-${DOMAIN:-}}"
  domain="${domain%%:*}"
  domain="${domain// /}"
  if [[ -n "$domain" ]]; then
    echo "$domain"
    return 0
  fi
  if nginx_server_primary_ip; then
    return 0
  fi
  hostname -f 2>/dev/null || hostname
}

# Подставить SSL_CERT/SSL_KEY из .env, Let's Encrypt или самоподписанного cert (без повторного ввода).
nginx_resolve_existing_ssl_paths() {
  local domain="${1:-${DOMAIN:-}}"
  domain="${domain%%:*}"

  if [[ -n "${SSL_CERT:-}" && -n "${SSL_KEY:-}" ]]; then
    return 0
  fi

  local cert key
  cert="$(nginx_env_get SSL_CERT)"
  key="$(nginx_env_get SSL_KEY)"
  if [[ -f "$cert" && -f "$key" ]]; then
    SSL_CERT="$cert"
    SSL_KEY="$key"
    return 0
  fi

  if [[ -n "$domain" ]]; then
    cert="/etc/letsencrypt/live/${domain}/fullchain.pem"
    key="/etc/letsencrypt/live/${domain}/privkey.pem"
    if [[ -f "$cert" && -f "$key" ]]; then
      SSL_CERT="$cert"
      SSL_KEY="$key"
      return 0
    fi
  fi

  if [[ -f "$NGINX_SELF_SIGNED_CERT" && -f "$NGINX_SELF_SIGNED_KEY" ]]; then
    SSL_CERT="$NGINX_SELF_SIGNED_CERT"
    SSL_KEY="$NGINX_SELF_SIGNED_KEY"
    return 0
  fi

  return 1
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

nginx_normalize_access_path() {
  local raw="${1:-}"
  raw="${raw// /}"
  raw="${raw#/}"
  raw="${raw%/}"
  if [[ -z "$raw" ]]; then
    printf ''
    return 0
  fi
  if [[ "$raw" == *".."* ]]; then
    nginx_die "ACCESS_PATH не должен содержать '..'"
  fi
  if [[ ! "$raw" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*(/[a-zA-Z0-9][a-zA-Z0-9_-]*)*$ ]]; then
    nginx_die "Некорректный ACCESS_PATH: ${raw}"
  fi
  printf '/%s' "$raw"
}

nginx_access_path_suffix() {
  local access_path="$1"
  if [[ -z "$access_path" ]]; then
    printf '/'
  else
    printf '%s/' "$access_path"
  fi
}

nginx_render_subpath_template() {
  local access_path="$1"
  local backend_port="$2"
  sed \
    -e "s|__ACCESS_PATH__|${access_path}|g" \
    -e "s|__BACKEND_PORT__|${backend_port}|g" \
    "$NGINX_TEMPLATE_DIR/adminpanelaz-subpath.conf.template"
}

nginx_root_panel_location_blocks() {
  local backend_port="$1"
  cat <<EOF
    # Telegram Mini App — без X-Frame-Options (WebView Telegram блокируется SAMEORIGIN)
    location ^~ /api/tg-mini {
        proxy_pass http://127.0.0.1:${backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        add_header Strict-Transport-Security "max-age=63072000" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
    }

    # API, SPA, WebSocket (/api/server-monitor/ws)
    location / {
        proxy_pass http://127.0.0.1:${backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
EOF
}

nginx_subpath_root_guard_blocks() {
  local access_path="$1"
  [[ -n "$access_path" ]] || return 0
  cat <<'EOF'

    # Корень и прочие пути вне подпути панели — plain 404 (без HTML nginx и без редиректа)
    location / {
        default_type text/plain;
        add_header Cache-Control "no-store" always;
        return 404 "Not Found";
    }
EOF
}

nginx_panel_location_blocks() {
  local access_path="$1"
  local backend_port="$2"
  if [[ -z "$access_path" ]]; then
    nginx_root_panel_location_blocks "$backend_port"
  else
    nginx_render_subpath_template "$access_path" "$backend_port"
    nginx_subpath_root_guard_blocks "$access_path"
  fi
}

nginx_has_vhost_for_domain() {
  local domain="$1"
  [[ -n "$domain" ]] || return 1
  local base path
  base="$(nginx_conf_basename "$domain")"
  [[ -f "/etc/nginx/sites-enabled/${base}" || -f "/etc/nginx/sites-available/${base}" ]] && return 0
  if grep -Rsl "server_name[^;]*\b${domain}\b" /etc/nginx/sites-enabled /etc/nginx/sites-available 2>/dev/null | grep -q .; then
    return 0
  fi
  return 1
}

nginx_is_our_panel_vhost_file() {
  local path="$1"
  [[ -f "$path" ]] || return 1
  grep -qE 'AdminPanelAZ —' "$path" 2>/dev/null
}

nginx_grep_vhosts_for_domain() {
  local domain="$1"
  local root="$2"
  [[ -n "$domain" && -n "$root" && -d "$root" ]] || return 0
  grep -Rsl "server_name[^;]*\\b${domain}\\b" "$root" 2>/dev/null || true
}

# sites-enabled первым: StatusOpenVPN и др. часто кладут копию в enabled, а не symlink.
nginx_list_vhosts_for_domain() {
  local domain="$1"
  [[ -n "$domain" ]] || return 0
  {
    nginx_grep_vhosts_for_domain "$domain" /etc/nginx/sites-enabled
    nginx_grep_vhosts_for_domain "$domain" /etc/nginx/sites-available
  } | awk '!seen[$0]++'
}

nginx_is_status_openvpn_vhost_file() {
  local path="$1"
  [[ -f "$path" ]] || return 1
  if grep -qF '# Created by StatusOpenVPN' "$path" 2>/dev/null; then
    return 0
  fi
  grep -qE 'location /status/' "$path" 2>/dev/null && grep -qF 'X-Script-Name /status' "$path" 2>/dev/null
}

nginx_list_status_openvpn_vhosts_for_domain() {
  local domain="$1"
  local path
  while IFS= read -r path; do
    [[ -n "$path" && -f "$path" ]] || continue
    nginx_is_status_openvpn_vhost_file "$path" || continue
    printf '%s\n' "$path"
  done < <(nginx_grep_vhosts_for_domain "$domain" /etc/nginx/sites-enabled)
}

nginx_has_status_openvpn_vhost_for_domain() {
  local domain="$1"
  nginx_list_status_openvpn_vhosts_for_domain "$domain" | grep -q .
}

nginx_list_foreign_vhosts_for_domain() {
  local domain="$1"
  local path
  while IFS= read -r path; do
    [[ -n "$path" && -f "$path" ]] || continue
    if nginx_is_our_panel_vhost_file "$path"; then
      continue
    fi
    printf '%s\n' "$path"
  done < <(nginx_list_vhosts_for_domain "$domain")
}

nginx_find_foreign_vhost_for_domain() {
  local domain="$1"
  local path
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    printf '%s\n' "$path"
    return 0
  done < <(nginx_list_foreign_vhosts_for_domain "$domain")
  return 1
}

nginx_has_foreign_vhost_for_domain() {
  local domain="$1"
  nginx_find_foreign_vhost_for_domain "$domain" >/dev/null
}

nginx_is_foreign_vhost_for_domain() {
  local domain="$1"
  nginx_has_foreign_vhost_for_domain "$domain"
}

nginx_remove_our_dedicated_sites_for_domain() {
  local domain="$1"
  local path base
  while IFS= read -r path; do
    [[ -n "$path" && -f "$path" ]] || continue
    if ! nginx_is_our_panel_vhost_file "$path"; then
      continue
    fi
    base="$(basename "$path")"
    rm -f "/etc/nginx/sites-enabled/${base}"
    rm -f "$path"
    nginx_log "Удалён выделенный vhost панели: ${path}"
  done < <(nginx_list_vhosts_for_domain "$domain")
}

nginx_subpath_snippet_basename() {
  local domain="$1"
  local access_path="$2"
  local domain_slug path_slug
  domain_slug="$(nginx_conf_basename "$domain")"
  path_slug="${access_path#/}"
  path_slug="${path_slug//\//_}"
  printf 'adminpanelaz-%s-%s' "$domain_slug" "$path_slug"
}

nginx_install_subpath_snippet() {
  local access_path="$1"
  local backend_port="$2"
  local domain="$3"
  local snippet_name snippet_path content
  snippet_name="$(nginx_subpath_snippet_basename "$domain" "$access_path")"
  snippet_path="/etc/nginx/snippets/${snippet_name}.conf"
  mkdir -p /etc/nginx/snippets /etc/nginx/backups
  content="$(nginx_render_subpath_template "$access_path" "$backend_port")"
  printf '%s\n' "$content" >"$snippet_path"
  nginx_log "Snippet subpath: ${snippet_path}"
  nginx_log "Добавьте в server { } для ${domain}: include snippets/${snippet_name}.conf;"
  NGINX_SUBPATH_SNIPPET_PATH="$snippet_path"
  NGINX_SUBPATH_SNIPPET_INCLUDE="snippets/${snippet_name}.conf"
}

_nginx_integrate_subpath_into_vhost_file() {
  local target="$1"
  local include_line="$2"
  local backup stamp
  [[ -n "$target" && -f "$target" && -n "$include_line" ]] || return 1
  if grep -qF "include ${include_line}" "$target"; then
    nginx_log "Include уже присутствует в ${target}"
    return 0
  fi
  stamp="$(date +%Y%m%d%H%M%S)"
  backup="/etc/nginx/backups/$(basename "$target").${stamp}.bak"
  cp "$target" "$backup"
  INCLUDE_LINE="$include_line" TARGET_FILE="$target" python3 - <<'PY'
import os
import re

path = os.environ["TARGET_FILE"]
include = os.environ["INCLUDE_LINE"]
text = open(path, encoding="utf-8").read()
if f"include {include}" in text:
    raise SystemExit(0)
match = re.search(r"listen\s+443[^\n]*", text)
if not match:
    raise SystemExit(1)
insert_at = match.end()
text = text[:insert_at] + f"\n\n    include {include};" + text[insert_at:]
open(path, "w", encoding="utf-8").write(text)
PY
  nginx_log "Include добавлен в ${target} (бэкап: ${backup})"
}

_nginx_assert_status_openvpn_vhost_intact() {
  local target="$1"
  [[ -f "$target" ]] || return 1
  grep -qE 'location /status/' "$target" && grep -qF 'X-Script-Name /status' "$target"
}

nginx_integrate_subpath_snippet_status_openvpn() {
  local domain="$1"
  local include_line="$2"
  local target integrated=0
  [[ -n "$domain" && -n "$include_line" ]] || return 1
  while IFS= read -r target; do
    [[ -n "$target" && -f "$target" ]] || continue
    _nginx_integrate_subpath_into_vhost_file "$target" "$include_line" || continue
    if ! _nginx_assert_status_openvpn_vhost_intact "$target"; then
      nginx_die "Интеграция нарушила конфиг StatusOpenVPN (${target}) — восстановите из /etc/nginx/backups/"
    fi
    nginx_log "StatusOpenVPN: блок /status/ сохранён в ${target}"
    integrated=1
  done < <(nginx_list_status_openvpn_vhosts_for_domain "$domain")
  if [[ "$integrated" -eq 0 ]]; then
    nginx_warn "Не найден активный StatusOpenVPN vhost в sites-enabled для ${domain}"
    return 1
  fi
}

nginx_integrate_subpath_snippet() {
  local domain="$1"
  local include_line="$2"
  local target integrated=0
  [[ -n "$domain" && -n "$include_line" ]] || return 1
  while IFS= read -r target; do
    [[ -n "$target" && -f "$target" ]] || continue
    _nginx_integrate_subpath_into_vhost_file "$target" "$include_line" && integrated=1
  done < <(nginx_list_foreign_vhosts_for_domain "$domain")
  if [[ "$integrated" -eq 0 ]]; then
    nginx_warn "Не найден сторонний vhost для ${domain} — добавьте include вручную: include ${include_line};"
    return 1
  fi
}

# Удалить subpath-snippet'ы панели с домена (при возврате на корень или смене пути).
nginx_cleanup_subpath_snippets_for_domain() {
  local domain="$1"
  [[ -n "$domain" ]] || return 0

  mkdir -p /etc/nginx/backups
  local target stamp backup
  while IFS= read -r target; do
    [[ -n "$target" && -f "$target" ]] || continue
    if ! grep -qF "$domain" "$target"; then
      continue
    fi
    if ! grep -qF 'include snippets/adminpanelaz-' "$target"; then
      continue
    fi
    stamp="$(date +%Y%m%d%H%M%S)"
    backup="/etc/nginx/backups/$(basename "$target").${stamp}.bak"
    cp "$target" "$backup"
    sed -i '\|include snippets/adminpanelaz-|d' "$target"
    nginx_log "Удалён subpath include из ${target} (бэкап: ${backup})"
  done < <(grep -Rsl "server_name" /etc/nginx/sites-enabled /etc/nginx/sites-available 2>/dev/null || true)

  local domain_slug snippet
  domain_slug="$(nginx_conf_basename "$domain")"
  shopt -s nullglob
  for snippet in /etc/nginx/snippets/adminpanelaz-"${domain_slug}"-*.conf; do
    rm -f "$snippet"
    nginx_log "Удалён snippet: ${snippet}"
  done
  shopt -u nullglob
}

nginx_render_template() {
  local template="$1"
  local domain="$2"
  local backend_port="$3"
  local ssl_cert="${4:-}"
  local ssl_key="${5:-}"
  local https_port="${6:-443}"
  local http_port="${7:-80}"
  local https_redirect_suffix access_path panel_blocks rendered
  https_redirect_suffix="$(nginx_https_redirect_suffix "$https_port")"
  access_path="$(nginx_normalize_access_path "${ACCESS_PATH:-}")"
  panel_blocks="$(nginx_panel_location_blocks "$access_path" "$backend_port")"
  rendered="$(sed \
    -e "s|__DOMAIN__|${domain}|g" \
    -e "s|__BACKEND_PORT__|${backend_port}|g" \
    -e "s|__HTTPS_PORT__|${https_port}|g" \
    -e "s|__HTTPS_REDIRECT_SUFFIX__|${https_redirect_suffix}|g" \
    -e "s|__HTTP_PORT__|${http_port}|g" \
    -e "s|__SSL_CERT__|${ssl_cert}|g" \
    -e "s|__SSL_KEY__|${ssl_key}|g" \
    -e "s|__UVICORN_PORT__|${backend_port}|g" \
    "$template")"
  ACCESS_PATH="$access_path" PANEL_BLOCKS="$panel_blocks" RENDERED="$rendered" python3 - <<'PY'
import os
print(os.environ["RENDERED"].replace("__PANEL_LOCATION_BLOCKS__", os.environ["PANEL_BLOCKS"]), end="")
PY
}

nginx_count_other_enabled_sites() {
  local domain="$1"
  local count=0
  local base=""
  [[ -n "$domain" ]] && base="$(nginx_conf_basename "$domain")"
  local path name
  for path in /etc/nginx/sites-enabled/*; do
    [[ -e "$path" ]] || continue
    name="$(basename "$path")"
    [[ -n "$base" && "$name" == "$base" ]] && continue
    [[ "$name" == "default" ]] && continue
    count=$((count + 1))
  done
  printf '%s' "$count"
}

# Убрать vhost панели и остановить nginx, если других сайтов нет.
# Редирект 443 → uvicorn больше не создаём — в режиме uvicorn панель слушает сама.
nginx_disable_for_direct_publish() {
  local domain="${1:-}"

  if [[ -n "$domain" ]]; then
    nginx_remove_site "$domain"
  fi

  command -v nginx >/dev/null 2>&1 || return 0

  local other
  other="$(nginx_count_other_enabled_sites "$domain")"
  if [[ "${other:-0}" -gt 0 ]]; then
    nginx_warn "Nginx оставлен запущенным: на сервере есть другие сайты (${other}). Панель — напрямую на своём порту."
    return 0
  fi

  systemctl stop nginx 2>/dev/null || true
  systemctl disable nginx 2>/dev/null || true
  nginx_log "Nginx остановлен (публикация без reverse proxy)"
}

nginx_set_publish_mode() {
  local mode="$1"
  [[ -n "$mode" ]] || return 0
  nginx_env_set PUBLISH_MODE "$mode"
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

nginx_clear_app_ssl_env() {
  nginx_env_unset USE_HTTPS
  nginx_env_unset SSL_CERT
  nginx_env_unset SSL_KEY
}

nginx_update_cors_for_direct_https() {
  local domain="$1"
  local https_port="${2:-443}"
  local public_host
  public_host="$(nginx_public_origin_host "$domain" "$https_port")"
  local origins="https://${public_host}"
  origins+=",http://127.0.0.1:${https_port},http://localhost:${https_port}"
  origins+=",http://127.0.0.1:5173,http://localhost:5173"
  nginx_env_set CORS_ORIGINS "$origins"
}

nginx_apply_behind_proxy_env() {
  local domain="$1"
  local backend_port="$2"
  local scheme="${3:-https}"
  local https_public_port="${4:-${HTTPS_PUBLIC_PORT:-443}}"
  local http_acme_port="${5:-${HTTP_ACME_PORT:-80}}"

  nginx_clear_app_ssl_env
  nginx_env_set BACKEND_HOST "127.0.0.1"
  nginx_env_set BACKEND_PORT "$backend_port"
  nginx_env_set DOMAIN "$domain"
  nginx_env_set BEHIND_NGINX "true"
  nginx_env_set HTTPS_PUBLIC_PORT "$https_public_port"
  nginx_env_set HTTP_ACME_PORT "$http_acme_port"
  nginx_env_set TRUSTED_PROXY_IPS "127.0.0.1"
  nginx_env_set FORWARDED_ALLOW_IPS "127.0.0.1"
  nginx_env_set REFRESH_TOKEN_COOKIE_SECURE "true"
  nginx_env_set ENFORCE_HTTPS "true"
  local normalized_access_path
  normalized_access_path="$(nginx_normalize_access_path "${ACCESS_PATH:-}")"
  if [[ -n "$normalized_access_path" ]]; then
    nginx_env_set ACCESS_PATH "$normalized_access_path"
  else
    nginx_env_unset ACCESS_PATH
  fi
  nginx_update_cors_for_domain "$domain" "$scheme" "$https_public_port"
}

nginx_apply_direct_https_env() {
  local domain="$1"
  local backend_port="$2"
  local ssl_cert="$3"
  local ssl_key="$4"
  local enforce_https="${5:-true}"

  nginx_env_set BACKEND_HOST "0.0.0.0"
  nginx_env_set BACKEND_PORT "$backend_port"
  nginx_env_set DOMAIN "$domain"
  nginx_env_set BEHIND_NGINX "false"
  nginx_env_set USE_HTTPS "true"
  nginx_env_set SSL_CERT "$ssl_cert"
  nginx_env_set SSL_KEY "$ssl_key"
  nginx_env_set HTTPS_PUBLIC_PORT "$backend_port"
  nginx_env_unset HTTP_ACME_PORT
  nginx_env_unset TRUSTED_PROXY_IPS
  nginx_env_unset FORWARDED_ALLOW_IPS
  nginx_env_set REFRESH_TOKEN_COOKIE_SECURE "true"
  if [[ "$enforce_https" == "true" ]]; then
    nginx_env_set ENFORCE_HTTPS "true"
  else
    nginx_env_unset ENFORCE_HTTPS
  fi
  nginx_env_unset ACCESS_PATH
  nginx_update_cors_for_direct_https "$domain" "$backend_port"
}

nginx_apply_direct_http_env() {
  local backend_port="$1"
  nginx_clear_app_ssl_env
  nginx_env_set BACKEND_HOST "0.0.0.0"
  nginx_env_set BACKEND_PORT "$backend_port"
  nginx_env_unset DOMAIN
  nginx_env_set BEHIND_NGINX "false"
  nginx_env_unset HTTPS_PUBLIC_PORT
  nginx_env_unset HTTP_ACME_PORT
  nginx_env_unset TRUSTED_PROXY_IPS
  nginx_env_unset FORWARDED_ALLOW_IPS
  nginx_env_unset ENFORCE_HTTPS
  nginx_env_unset REFRESH_TOKEN_COOKIE_SECURE
  nginx_env_unset ACCESS_PATH
}

nginx_remove_all_vhosts_for_domain() {
  local domain="$1"
  [[ -n "$domain" ]] || return 0

  mkdir -p /etc/nginx/backups
  local path stamp backup base
  declare -A seen=()
  while IFS= read -r path; do
    [[ -n "$path" && -f "$path" ]] || continue
    [[ -n "${seen[$path]:-}" ]] && continue
    seen[$path]=1
    stamp="$(date +%Y%m%d%H%M%S)"
    backup="/etc/nginx/backups/$(basename "$path").repair.${stamp}.bak"
    cp "$path" "$backup"
    nginx_log "Бэкап vhost: ${backup}"
    base="$(basename "$path")"
    rm -f "$path" "/etc/nginx/sites-enabled/${base}" "/etc/nginx/sites-available/${base}"
    nginx_log "Удалён vhost: ${path}"
  done < <(nginx_list_vhosts_for_domain "$domain")
}

nginx_resolve_panel_ssl_cert_paths() {
  local domain="$1"
  local le_cert="/etc/letsencrypt/live/${domain}/fullchain.pem"
  local le_key="/etc/letsencrypt/live/${domain}/privkey.pem"
  local cert key

  if [[ -f "$le_cert" && -f "$le_key" ]]; then
    NGINX_SSL_CERT="$le_cert"
    NGINX_SSL_KEY="$le_key"
    return 0
  fi

  cert="$(nginx_env_get SSL_CERT)"
  key="$(nginx_env_get SSL_KEY)"
  if [[ -n "$cert" && -n "$key" && -f "$cert" && -f "$key" ]]; then
    NGINX_SSL_CERT="$cert"
    NGINX_SSL_KEY="$key"
    return 0
  fi

  if [[ -f "$NGINX_SELF_SIGNED_CERT" && -f "$NGINX_SELF_SIGNED_KEY" ]]; then
    NGINX_SSL_CERT="$NGINX_SELF_SIGNED_CERT"
    NGINX_SSL_KEY="$NGINX_SELF_SIGNED_KEY"
    return 0
  fi

  return 1
}

nginx_install_dedicated_panel_vhost() {
  local domain="$1"
  local backend_port="$2"
  local ssl_cert="$3"
  local ssl_key="$4"
  local https_port="${5:-443}"
  local http_port="${6:-80}"
  local conf

  conf="$(nginx_render_template \
    "$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template" \
    "$domain" "$backend_port" "$ssl_cert" "$ssl_key" "$https_port" "$http_port")"
  nginx_install_site "$conf" "$domain"
}

nginx_install_site() {
  local conf_content="$1"
  local domain="$2"
  local reload_only="${3:-false}"

  nginx_conf_paths "$domain"
  printf '%s\n' "$conf_content" >"$NGINX_CONF_FILE"
  ln -sf "$NGINX_CONF_FILE" "$NGINX_ENABLED_LINK"
  # Стандартный default мешает: на корне домена показывается «Welcome to nginx».
  rm -f /etc/nginx/sites-enabled/default
  nginx -t || nginx_die "nginx -t не прошёл (конфиг: $NGINX_CONF_FILE)"
  systemctl enable nginx >/dev/null 2>&1 || true
  if [[ "$reload_only" == "true" ]]; then
    systemctl reload nginx || nginx_die "Не удалось перезагрузить nginx"
  else
    systemctl restart nginx || nginx_die "Не удалось запустить nginx"
  fi
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
  mkdir -p /var/www/html/.well-known/acme-challenge

  local certbot_ok=false
  if systemctl is-active nginx >/dev/null 2>&1; then
    nginx_log "Пробуем certbot webroot (nginx остаётся запущенным)…"
    if [[ -n "$email" ]]; then
      certbot certonly --webroot -w /var/www/html --non-interactive --agree-tos -m "$email" -d "$domain" && certbot_ok=true || true
    else
      certbot certonly --webroot -w /var/www/html --non-interactive --agree-tos --register-unsafely-without-email -d "$domain" && certbot_ok=true || true
    fi
  fi

  if [[ "$certbot_ok" == "true" && -f "$cert_path" ]]; then
    nginx_log "Сертификат Let's Encrypt получен через webroot"
    return 0
  fi

  nginx_log "Webroot не сработал — certbot standalone (nginx будет остановлен)…"
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
  systemctl start nginx 2>/dev/null || true
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
