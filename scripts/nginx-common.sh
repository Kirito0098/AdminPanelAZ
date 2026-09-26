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
  # stderr: callers often capture stdout (e.g. conf="$(nginx_render_template …)")
  echo "[nginx-setup] $*" >&2
}

nginx_warn() {
  echo "[nginx-setup] ВНИМАНИЕ: $*" >&2
}

nginx_die() {
  echo "[nginx-setup] ОШИБКА: $*" >&2
  exit 1
}

# Путь к setup AntiZapret (OPENVPN_HOST / WIREGUARD_HOST).
nginx_az_setup_path() {
  echo "${ANTIZAPRET_PATH:-/root/antizapret}/setup"
}

# Прочитать значение KEY= из setup AZ (пусто, если файла/ключа нет).
nginx_read_az_setup_value() {
  local key="$1"
  local setup
  setup="$(nginx_az_setup_path)"
  [[ -f "$setup" ]] || return 0
  grep -E "^${key}=" "$setup" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true
}

# Нормализация host для сравнения с доменом панели.
nginx_normalize_host() {
  local host="${1:-}"
  host="${host%%:*}"
  host="${host%%/*}"
  host="${host,,}"
  host="${host%.}"
  echo "$host"
}

nginx_suggest_portal_domain() {
  local host labels first rest
  host="$(nginx_normalize_host "${1:-}")"
  [[ -n "$host" ]] || { printf ''; return 0; }
  if [[ "$host" == portal.* ]]; then
    rest="${host#portal.}"
    if [[ -n "$rest" ]]; then
      printf 'clients.%s' "$rest"
    else
      printf ''
    fi
    return 0
  fi
  IFS='.' read -r -a labels <<<"$host"
  first="${labels[0]:-}"
  if ((${#labels[@]} >= 3)) && [[ "$first" =~ ^(panel|admin|app|ui|cp|manage)$ ]]; then
    printf 'portal.%s' "${host#${first}.}"
    return 0
  fi
  printf 'portal.%s' "$host"
}

nginx_is_nested_portal_host() {
  local portal panel
  portal="$(nginx_normalize_host "${1:-}")"
  panel="$(nginx_normalize_host "${2:-}")"
  [[ -n "$portal" && -n "$panel" ]] || return 1
  [[ "$portal" == "portal.${panel}" ]]
}

# Сообщение о конфликте DOMAIN с AZ hosts; 0 = ок, 1 = конфликт (текст в stdout).
nginx_az_vpn_host_conflict_message() {
  local domain
  domain="$(nginx_normalize_host "${1:-}")"
  [[ -n "$domain" ]] || return 0

  local ovpn wg
  ovpn="$(nginx_normalize_host "$(nginx_read_az_setup_value OPENVPN_HOST)")"
  wg="$(nginx_normalize_host "$(nginx_read_az_setup_value WIREGUARD_HOST)")"

  local matched=""
  if [[ -n "$ovpn" && "$domain" == "$ovpn" ]]; then
    matched="OPENVPN_HOST=${ovpn}"
  fi
  if [[ -n "$wg" && "$domain" == "$wg" ]]; then
    if [[ -n "$matched" ]]; then
      matched="${matched}, WIREGUARD_HOST=${wg}"
    else
      matched="WIREGUARD_HOST=${wg}"
    fi
  fi
  [[ -z "$matched" ]] && return 0

  echo "Домен панели «${domain}» совпадает с ${matched} в $(nginx_az_setup_path). Через конфиг AntiZapret этот адрес уходит в туннель — локальная панель станет недоступна. Укажите отдельный домен для панели (например panel.example.com)."
  return 1
}

# Запрет: DOMAIN панели = OPENVPN_HOST или WIREGUARD_HOST (иначе панель недоступна через AZ).
nginx_assert_domain_not_az_vpn_host() {
  local msg=""
  if ! msg="$(nginx_az_vpn_host_conflict_message "${1:-}")"; then
    nginx_die "$msg"
  fi
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

nginx_sites_available_dir() {
  printf '%s' "${NGINX_SITES_AVAILABLE_DIR:-/etc/nginx/sites-available}"
}

nginx_sites_enabled_dir() {
  printf '%s' "${NGINX_SITES_ENABLED_DIR:-/etc/nginx/sites-enabled}"
}

nginx_conf_d_dir() {
  printf '%s' "${NGINX_CONF_D_DIR:-/etc/nginx/conf.d}"
}

nginx_conf_paths() {
  local domain="$1"
  local base
  base="$(nginx_conf_basename "$domain")"
  NGINX_CONF_FILE="$(nginx_sites_available_dir)/${base}"
  NGINX_ENABLED_LINK="$(nginx_sites_enabled_dir)/${base}"
}

# Long FQDNs (e.g. portal.panel.example.com) need a larger hash bucket than nginx defaults (32/64).
# Sets NGINX_HASH_SNIPPET_* for transactional rollback from nginx_install_site.
nginx_server_names_hash_dest() {
  printf '%s/adminpanelaz-server-names-hash.conf' "$(nginx_conf_d_dir)"
}

nginx_hash_bucket_size_from_file() {
  local f="$1" size=""
  [[ -f "$f" ]] || {
    printf '0'
    return 0
  }
  size="$(grep -E '^\s*server_names_hash_bucket_size\s+[0-9]+' "$f" 2>/dev/null | head -1 | awk '{print $2}' | tr -d ';' || true)"
  if [[ "$size" =~ ^[0-9]+$ ]]; then
    printf '%s' "$size"
  else
    printf '0'
  fi
}

nginx_ensure_server_names_hash() {
  local src dest dir existing_size
  local required=128
  src="${NGINX_TEMPLATE_DIR}/adminpanelaz-server-names-hash.conf"
  dir="$(nginx_conf_d_dir)"
  dest="$(nginx_server_names_hash_dest)"
  [[ -f "$src" ]] || nginx_die "Нет шаблона server_names_hash: ${src}"
  mkdir -p "$dir"

  NGINX_HASH_SNIPPET_DEST="$dest"
  NGINX_HASH_SNIPPET_BAK=""
  NGINX_HASH_SNIPPET_CREATED=false
  NGINX_HASH_SNIPPET_CHANGED=false

  if [[ -f "$dest" ]]; then
    if cmp -s "$src" "$dest"; then
      return 0
    fi
    existing_size="$(nginx_hash_bucket_size_from_file "$dest")"
    if (( existing_size >= required )); then
      nginx_log "Snippet server_names_hash уже достаточный (bucket_size=${existing_size}): ${dest}"
      return 0
    fi
    NGINX_HASH_SNIPPET_BAK="${dest}.apaz-hash.bak.$$"
    cp -a "$dest" "$NGINX_HASH_SNIPPET_BAK"
    cp "$src" "$dest"
    NGINX_HASH_SNIPPET_CHANGED=true
  else
    cp "$src" "$dest"
    NGINX_HASH_SNIPPET_CREATED=true
    NGINX_HASH_SNIPPET_CHANGED=true
  fi
  nginx_log "Snippet server_names_hash: ${dest}"
}

nginx_rollback_server_names_hash() {
  local dest="${NGINX_HASH_SNIPPET_DEST:-}"
  [[ -n "$dest" ]] || return 0
  [[ "${NGINX_HASH_SNIPPET_CHANGED:-false}" == "true" ]] || return 0
  if [[ -n "${NGINX_HASH_SNIPPET_BAK:-}" && -f "$NGINX_HASH_SNIPPET_BAK" ]]; then
    mv -f "$NGINX_HASH_SNIPPET_BAK" "$dest"
  elif [[ "${NGINX_HASH_SNIPPET_CREATED:-false}" == "true" ]]; then
    rm -f "$dest"
  fi
  NGINX_HASH_SNIPPET_CHANGED=false
  NGINX_HASH_SNIPPET_BAK=""
  NGINX_HASH_SNIPPET_CREATED=false
}

nginx_cleanup_server_names_hash_bak() {
  if [[ -n "${NGINX_HASH_SNIPPET_BAK:-}" && -f "$NGINX_HASH_SNIPPET_BAK" ]]; then
    rm -f "$NGINX_HASH_SNIPPET_BAK"
  fi
  NGINX_HASH_SNIPPET_BAK=""
}

# Refuse to stop a live nginx when disk config already fails nginx -t.
nginx_assert_config_ok_before_stop() {
  if ! command -v nginx >/dev/null 2>&1; then
    return 0
  fi
  if ! nginx -t >/dev/null 2>&1; then
    nginx_die "nginx -t сейчас не проходит — standalone не будет останавливать nginx. Удалите битый site из sites-enabled/conf.d или исправьте конфиг, затем повторите."
  fi
}

nginx_tcp_port_is_listening() {
  local port="$1" line addr
  [[ "$port" =~ ^[0-9]+$ ]] || return 1
  command -v ss >/dev/null 2>&1 || return 1
  while IFS= read -r line; do
    addr="$(printf '%s\n' "$line" | awk '{print $4}')"
    case "$addr" in
      *":${port}" | *":${port}]") return 0 ;;
    esac
  done < <(ss -tlnH 2>/dev/null || ss -tln 2>/dev/null | tail -n +2 || true)
  return 1
}

nginx_describe_tcp_port_listeners() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tlnp "sport = :${port}" 2>/dev/null || ss -tlnp 2>/dev/null | grep -E ":${port}\\b" || true
  else
    printf '(ss недоступен — не удалось перечислить слушателей порта %s)\n' "$port"
  fi
}

nginx_assert_ss_for_tcp_port_check() {
  if ! command -v ss >/dev/null 2>&1; then
    nginx_die "Для проверки, что TCP-порт свободен перед certbot standalone, нужна утилита ss (пакет iproute2). Установите ss и повторите настройку портала."
  fi
}

nginx_wait_tcp_port_free() {
  local port="${1:-80}"
  local attempts="${2:-20}"
  local i
  nginx_assert_ss_for_tcp_port_check
  for ((i = 1; i <= attempts; i++)); do
    if ! nginx_tcp_port_is_listening "$port"; then
      return 0
    fi
    sleep 0.25
  done
  nginx_die "Порт ${port} всё ещё занят после остановки nginx (Let's Encrypt standalone нужен свободный IPv4 :${port}). Слушатели:
$(nginx_describe_tcp_port_listeners "$port")
Остановите процесс на :${port} и повторите настройку портала."
}

nginx_stop_for_standalone_acme() {
  local http_port="${1:-80}"
  nginx_assert_config_ok_before_stop
  nginx_assert_ss_for_tcp_port_check
  if systemctl is-active --quiet nginx 2>/dev/null || nginx_tcp_port_is_listening "$http_port"; then
    nginx_log "Останавливаем nginx, чтобы освободить порт ${http_port} для certbot standalone…"
    NGINX_STOPPED_FOR_ACME=true
    if ! systemctl stop nginx; then
      nginx_die "Не удалось остановить nginx перед certbot standalone (порт ${http_port}). Исправьте unit/nginx и повторите."
    fi
  fi
  if nginx_tcp_port_is_listening "$http_port"; then
    nginx_log "Порт ${http_port} ещё занят — ждём освобождения…"
  fi
  nginx_wait_tcp_port_free "$http_port" 40
}

nginx_acme_temp_site_basename() {
  local domain="$1"
  printf 'adminpanelaz-acme-%s' "$(nginx_conf_basename "$domain")"
}

nginx_acme_default_stash_paths() {
  local base="$1"
  local enabled_dir
  enabled_dir="$(nginx_sites_enabled_dir)"
  NGINX_ACME_DEFAULT_STASH="${enabled_dir}/.adminpanelaz-acme-default-stash-${base}"
  NGINX_ACME_DEFAULT_STASH_COPY="${NGINX_ACME_DEFAULT_STASH}.copy"
}

# Remember sites-enabled/default before temp ACME removes it (restore on failure or remove helper).
nginx_acme_stash_enabled_default() {
  local base="$1"
  local enabled_dir default_path stash copy_path target
  enabled_dir="$(nginx_sites_enabled_dir)"
  default_path="${enabled_dir}/default"
  nginx_acme_default_stash_paths "$base"
  stash="$NGINX_ACME_DEFAULT_STASH"
  copy_path="$NGINX_ACME_DEFAULT_STASH_COPY"
  [[ -e "$stash" ]] && return 0
  [[ -e "$default_path" || -L "$default_path" ]] || return 0
  if [[ -L "$default_path" ]]; then
    target="$(readlink "$default_path" 2>/dev/null || true)"
    [[ -n "$target" ]] || return 0
    printf 'symlink\n%s\n' "$target" >"$stash"
  elif [[ -f "$default_path" ]]; then
    cp -a "$default_path" "$copy_path"
    printf 'file\n%s\n' "$copy_path" >"$stash"
  fi
}

nginx_acme_restore_enabled_default() {
  local base="$1"
  local enabled_dir default_path stash copy_path kind target
  enabled_dir="$(nginx_sites_enabled_dir)"
  default_path="${enabled_dir}/default"
  nginx_acme_default_stash_paths "$base"
  stash="$NGINX_ACME_DEFAULT_STASH"
  copy_path="$NGINX_ACME_DEFAULT_STASH_COPY"
  [[ -f "$stash" ]] || return 0
  kind="$(sed -n '1p' "$stash")"
  target="$(sed -n '2p' "$stash")"
  rm -f "$stash" "$copy_path"
  case "$kind" in
    symlink)
      [[ -n "$target" ]] || return 0
      ln -sf "$target" "$default_path"
      ;;
    file)
      [[ -n "$target" && -f "$target" ]] || return 0
      cp -a "$target" "$default_path"
      rm -f "$target"
      ;;
  esac
}

# Temporary HTTP-only vhost so certbot --webroot works before the real portal HTTPS site exists.
nginx_install_temp_acme_http_vhost() {
  local domain="$1"
  local http_port="${2:-80}"
  local base available_dir enabled_dir conf_file enabled_link conf
  domain="$(nginx_normalize_host "$domain")"
  [[ -n "$domain" ]] || return 0
  http_port="${http_port:-80}"

  nginx_ensure_server_names_hash
  mkdir -p /var/www/html/.well-known/acme-challenge
  base="$(nginx_acme_temp_site_basename "$domain")"
  available_dir="$(nginx_sites_available_dir)"
  enabled_dir="$(nginx_sites_enabled_dir)"
  mkdir -p "$available_dir" "$enabled_dir"
  conf_file="${available_dir}/${base}"
  enabled_link="${enabled_dir}/${base}"

  conf="$(cat <<EOF
# Temporary ACME webroot (AdminPanelAZ) — removed after cert issue / portal vhost install
server {
    listen ${http_port};
    listen [::]:${http_port};
    server_name ${domain};

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        default_type text/plain;
        return 404;
    }
}
EOF
)"
  printf '%s\n' "$conf" >"$conf_file"
  ln -sf "$conf_file" "$enabled_link"
  nginx_acme_stash_enabled_default "$base"
  rm -f "${enabled_dir}/default"

  if ! nginx -t >/dev/null 2>&1; then
    rm -f "$enabled_link" "$conf_file"
    nginx_acme_restore_enabled_default "$base"
    nginx_rollback_server_names_hash
    nginx_warn "Временный ACME vhost для ${domain} не прошёл nginx -t — пробуем без webroot"
    return 1
  fi
  nginx_cleanup_server_names_hash_bak
  if systemctl is-active --quiet nginx 2>/dev/null; then
    systemctl reload nginx >/dev/null 2>&1 || systemctl restart nginx >/dev/null 2>&1 || true
  else
    systemctl start nginx >/dev/null 2>&1 || true
  fi
  nginx_log "Временный ACME HTTP vhost: ${domain} (порт ${http_port})"
  return 0
}

nginx_remove_temp_acme_http_vhost() {
  local domain="$1"
  local base available_dir enabled_dir
  domain="$(nginx_normalize_host "$domain")"
  [[ -n "$domain" ]] || return 0
  base="$(nginx_acme_temp_site_basename "$domain")"
  available_dir="$(nginx_sites_available_dir)"
  enabled_dir="$(nginx_sites_enabled_dir)"
  rm -f "${enabled_dir}/${base}" "${available_dir}/${base}"
  nginx_acme_restore_enabled_default "$base"
  if systemctl is-active --quiet nginx 2>/dev/null; then
    nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || true
  fi
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
  local out
  out="$(sed \
    -e "s|__ACCESS_PATH__|${access_path}|g" \
    -e "s|__BACKEND_PORT__|${backend_port}|g" \
    "$NGINX_TEMPLATE_DIR/adminpanelaz-subpath.conf.template")"
  if ! nginx_cloudflare_proxy_enabled; then
    out="$(printf '%s\n' "$out" | sed '/include snippets\/cloudflare-realip.conf;/d')"
  fi
  if ! nginx_cloudflare_origin_lock_enabled; then
    out="$(printf '%s\n' "$out" | sed '/include snippets\/cloudflare-origin-lock.conf;/d')"
  fi
  printf '%s\n' "$out"
}

nginx_snippets_dir() {
  printf '%s' "${NGINX_SNIPPETS_DIR:-/etc/nginx/snippets}"
}

# Exported value (set by the panel when it regenerates nginx) wins; manual runs read ENV_FILE.
nginx_cloudflare_flag() {
  local key="$1" default="$2" v
  v="${!key:-}"
  if [[ -z "$v" ]]; then
    v="$(nginx_env_get "$key" | tr -d "\"'" | tr -d '[:space:]')"
  fi
  printf '%s' "${v:-$default}"
}

nginx_cloudflare_proxy_enabled() {
  local v
  v="$(nginx_cloudflare_flag CLOUDFLARE_PROXY_ENABLED true)"
  case "${v,,}" in
    true|1|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

nginx_cloudflare_origin_lock_enabled() {
  nginx_cloudflare_proxy_enabled || return 1
  local v
  v="$(nginx_cloudflare_flag CLOUDFLARE_ORIGIN_LOCK false)"
  case "${v,,}" in
    true|1|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

nginx_realip_include_line() {
  if nginx_cloudflare_proxy_enabled; then
    printf '        include snippets/cloudflare-realip.conf;\n'
  else
    printf ''
  fi
}

nginx_origin_lock_include_line() {
  if nginx_cloudflare_origin_lock_enabled; then
    printf '        include snippets/cloudflare-origin-lock.conf;\n'
  else
    printf ''
  fi
}

nginx_ensure_cloudflare_realip_snippet() {
  local src dest dir bak_dir
  src="${NGINX_TEMPLATE_DIR}/cloudflare-realip.conf"
  dir="$(nginx_snippets_dir)"
  dest="${dir}/cloudflare-realip.conf"
  bak_dir="${NGINX_BACKUPS_DIR:-/etc/nginx/backups}"
  [[ -f "$src" ]] || nginx_die "Нет шаблона Cloudflare realip: ${src}"
  mkdir -p "$dir" "$bak_dir"
  if [[ -f "$dest" ]] && ! cmp -s "$src" "$dest"; then
    cp "$dest" "${bak_dir}/cloudflare-realip.conf.$(date +%Y%m%d%H%M%S).bak"
  fi
  cp "$src" "$dest"
  nginx_log "Snippet Cloudflare realip: ${dest}"
}

nginx_ensure_cloudflare_origin_allow_snippet() {
  local src dest dir bak_dir
  src="${NGINX_TEMPLATE_DIR}/cloudflare-origin-allow.conf"
  dir="$(nginx_snippets_dir)"
  dest="${dir}/cloudflare-origin-allow.conf"
  bak_dir="${NGINX_BACKUPS_DIR:-/etc/nginx/backups}"
  [[ -f "$src" ]] || nginx_die "Нет шаблона Cloudflare origin allow: ${src}"
  mkdir -p "$dir" "$bak_dir"
  if [[ -f "$dest" ]] && ! cmp -s "$src" "$dest"; then
    cp "$dest" "${bak_dir}/cloudflare-origin-allow.conf.$(date +%Y%m%d%H%M%S).bak"
  fi
  cp "$src" "$dest"
  nginx_log "Snippet Cloudflare origin allow: ${dest}"
}

nginx_cloudflare_origin_geo_dest() {
  printf '%s/adminpanelaz-cloudflare-origin.conf' "$(nginx_conf_d_dir)"
}

# http-level geo keyed by the TCP peer: realip rewrites $remote_addr before the access
# phase, so origin lock cannot use allow/deny in locations that also trust CF-Connecting-IP.
nginx_render_cloudflare_origin_geo() {
  local allow_file="$1"
  [[ -f "$allow_file" ]] || nginx_die "Нет Cloudflare origin allow snippet: ${allow_file}"
  printf '# AdminPanelAZ — generated from snippets/cloudflare-origin-allow.conf; do not edit.\n'
  printf 'geo $realip_remote_addr $adminpanelaz_cf_origin {\n'
  printf '    default 0;\n'
  awk '
    {
      line = $0
      sub(/#.*/, "", line)
      if (line !~ /^[[:space:]]*allow[[:space:]]+[^;[:space:]]+[[:space:]]*;[[:space:]]*$/) { next }
      split(line, parts, /[[:space:];]+/)
      addr = (parts[1] == "") ? parts[3] : parts[2]
      if (addr == "all") { next }
      printf "    %s 1;\n", addr
    }
  ' "$allow_file"
  printf '}\n'
}

nginx_ensure_cloudflare_origin_geo_conf() {
  local allow_file dest dir bak_dir tmp
  allow_file="$(nginx_snippets_dir)/cloudflare-origin-allow.conf"
  dir="$(nginx_conf_d_dir)"
  dest="$(nginx_cloudflare_origin_geo_dest)"
  bak_dir="${NGINX_BACKUPS_DIR:-/etc/nginx/backups}"
  mkdir -p "$dir" "$bak_dir"
  tmp="${dest}.tmp.$$"
  nginx_render_cloudflare_origin_geo "$allow_file" >"$tmp"
  if [[ -f "$dest" ]] && ! cmp -s "$tmp" "$dest"; then
    cp "$dest" "${bak_dir}/adminpanelaz-cloudflare-origin.conf.$(date +%Y%m%d%H%M%S).bak"
  fi
  mv -f "$tmp" "$dest"
  nginx_log "Cloudflare origin geo: ${dest}"
}

nginx_ensure_cloudflare_origin_lock_snippet() {
  local src dest dir
  src="${NGINX_TEMPLATE_DIR}/cloudflare-origin-lock.conf"
  dir="$(nginx_snippets_dir)"
  dest="${dir}/cloudflare-origin-lock.conf"
  [[ -f "$src" ]] || nginx_die "Нет шаблона Cloudflare origin lock: ${src}"
  mkdir -p "$dir"
  cp "$src" "$dest"
}

# Allow list (source of truth) → conf.d geo → location-level lock snippet.
nginx_ensure_cloudflare_origin_snippets() {
  nginx_ensure_cloudflare_origin_allow_snippet
  nginx_ensure_cloudflare_origin_geo_conf
  nginx_ensure_cloudflare_origin_lock_snippet
}

# Restore <dest> from <bak>, or drop it if it did not exist before (<created>=true).
nginx_restore_file_from_backup() {
  local dest="$1" bak="$2" created="$3"
  if [[ -n "$bak" && -f "$bak" ]]; then
    mv -f "$bak" "$dest"
  elif [[ "$created" == true ]]; then
    rm -f "$dest"
  fi
}

nginx_cloudflare_snippets_apply() {
  local new_file="$1"
  local allow_file="${2:-}"
  local dir dest allow_dest geo_dest bak_dir tmp stamp
  local dest_bak="" allow_bak="" geo_bak=""
  local dest_created=false allow_created=false geo_created=false
  [[ -f "$new_file" ]] || nginx_die "Файл не найден: $new_file"
  [[ "$(id -u)" -eq 0 ]] || nginx_die "Запустите от root"
  if [[ -n "$allow_file" ]]; then
    [[ -f "$allow_file" ]] || nginx_die "Файл не найден: $allow_file"
  fi

  dir="$(nginx_snippets_dir)"
  dest="${dir}/cloudflare-realip.conf"
  allow_dest="${dir}/cloudflare-origin-allow.conf"
  geo_dest="$(nginx_cloudflare_origin_geo_dest)"
  bak_dir="${NGINX_BACKUPS_DIR:-/etc/nginx/backups}"
  stamp="$(date +%Y%m%d%H%M%S)"
  mkdir -p "$dir" "$bak_dir"

  if [[ -f "$dest" ]]; then
    dest_bak="${bak_dir}/cloudflare-realip.conf.${stamp}.bak"
    cp "$dest" "$dest_bak"
  else
    dest_created=true
  fi
  tmp="${dest}.tmp.$$"
  cp "$new_file" "$tmp"
  mv "$tmp" "$dest"

  if [[ -n "$allow_file" ]]; then
    if [[ -f "$allow_dest" ]]; then
      allow_bak="${bak_dir}/cloudflare-origin-allow.conf.${stamp}.bak"
      cp "$allow_dest" "$allow_bak"
    else
      allow_created=true
    fi
    tmp="${allow_dest}.tmp.$$"
    cp "$allow_file" "$tmp"
    mv "$tmp" "$allow_dest"

    if [[ -f "$geo_dest" ]]; then
      geo_bak="${bak_dir}/adminpanelaz-cloudflare-origin.conf.${stamp}.bak"
      cp "$geo_dest" "$geo_bak"
    else
      geo_created=true
    fi
    mkdir -p "$(dirname "$geo_dest")"
    tmp="${geo_dest}.tmp.$$"
    nginx_render_cloudflare_origin_geo "$allow_dest" >"$tmp"
    mv "$tmp" "$geo_dest"
  fi

  local failure=""
  if ! nginx -t; then
    failure="nginx -t не прошёл"
  elif ! systemctl reload nginx; then
    failure="Не удалось reload nginx"
  fi
  if [[ -n "$failure" ]]; then
    nginx_restore_file_from_backup "$dest" "$dest_bak" "$dest_created"
    if [[ -n "$allow_file" ]]; then
      nginx_restore_file_from_backup "$allow_dest" "$allow_bak" "$allow_created"
      nginx_restore_file_from_backup "$geo_dest" "$geo_bak" "$geo_created"
    fi
    nginx_die "${failure} — восстановлены предыдущие cloudflare snippets"
  fi
  nginx_log "Cloudflare realip snippet обновлён: ${dest}"
  if [[ -n "$allow_file" ]]; then
    nginx_log "Cloudflare origin allow snippet обновлён: ${allow_dest}"
    nginx_log "Cloudflare origin geo обновлён: ${geo_dest}"
  fi
}

nginx_cloudflare_realip_apply() {
  local new_file="$1"
  nginx_cloudflare_snippets_apply "$new_file"
}

nginx_root_panel_location_blocks() {
  local backend_port="$1"
  cat <<EOF
    # Telegram Bot API webhook
    location ^~ /api/telegram/webhook/ {
$(nginx_realip_include_line)
$(nginx_origin_lock_include_line)

        proxy_pass http://127.0.0.1:${backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    # Telegram Mini App — без X-Frame-Options (WebView Telegram блокируется SAMEORIGIN)
    location ^~ /api/tg-mini {
$(nginx_realip_include_line)
$(nginx_origin_lock_include_line)
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
$(nginx_realip_include_line)
$(nginx_origin_lock_include_line)
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

# Client portal host: only /p, /p/, /api/public/, /assets, /assets/ — else 404 (no admin SPA).
# Exact = /p and prefix ^~ /p/ so /password or /panel are not proxied.
nginx_portal_location_blocks() {
  local backend_port="$1"
  cat <<EOF
    location = /p {
$(nginx_realip_include_line)
        proxy_pass http://127.0.0.1:${backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    location ^~ /p/ {
$(nginx_realip_include_line)
        proxy_pass http://127.0.0.1:${backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    location ^~ /api/public/ {
$(nginx_realip_include_line)
        proxy_pass http://127.0.0.1:${backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    location = /assets {
$(nginx_realip_include_line)
        proxy_pass http://127.0.0.1:${backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location ^~ /assets/ {
$(nginx_realip_include_line)
        proxy_pass http://127.0.0.1:${backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        default_type text/plain;
        add_header Cache-Control "no-store" always;
        return 404 "Not Found";
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
  local escaped
  [[ -n "$domain" && -n "$root" && -d "$root" ]] || return 0
  # Whole server_name token: \b would also match portal.<domain> and delete the portal vhost on repair.
  escaped="$(printf '%s' "$domain" | sed 's/[][\.*^$()+?{}|]/\\&/g')"
  grep -RslE "^[[:space:]]*server_name([[:space:]]+[^;[:space:]]+)*[[:space:]]+${escaped}([[:space:];]|$)" "$root" 2>/dev/null || true
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
  nginx_ensure_cloudflare_realip_snippet
  nginx_ensure_cloudflare_origin_snippets
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
  nginx_ensure_cloudflare_realip_snippet
  nginx_ensure_cloudflare_origin_snippets
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

# Файлы с блоком server, кроме файлов панели и стандартной заглушки default. Список берётся
# из nginx -T: сайты бывают и в conf.d, и в любых include, а не только в sites-enabled.
nginx_count_other_enabled_sites() {
  local domain="$1"
  local count=0
  local base=""
  [[ -n "$domain" ]] && base="$(nginx_conf_basename "$domain")"
  local -a files=()
  mapfile -t files < <(nginx -T 2>/dev/null | sed -n 's/^# configuration file \(.*\):$/\1/p')
  if ((${#files[@]} == 0)); then
    files=("$(nginx_sites_enabled_dir)"/* "$(nginx_conf_d_dir)"/*.conf)
  fi
  local path name
  for path in "${files[@]}"; do
    [[ -f "$path" ]] || continue
    name="$(basename "$path")"
    [[ -n "$base" && "$name" == "$base" ]] && continue
    case "$name" in
      default | default.conf | adminpanelaz-* | 00-adminpanelaz-*) continue ;;
    esac
    sed 's/#.*//' "$path" | grep -Eq '(^|[[:space:];{}])server([[:space:]]*\{|[[:space:]]*$)' || continue
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
  # В режиме uvicorn панель сама слушает HTTPS-порт: сервер по умолчанию nginx занял бы его.
  nginx_remove_default_deny

  command -v nginx >/dev/null 2>&1 || return 0

  local other
  other="$(nginx_count_other_enabled_sites "$domain")"
  if [[ "${other:-0}" -gt 0 ]]; then
    nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || true
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
  nginx_set_publish_mode "http_direct"
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

  nginx_ensure_cloudflare_realip_snippet
  nginx_ensure_cloudflare_origin_snippets
  conf="$(nginx_render_template \
    "$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template" \
    "$domain" "$backend_port" "$ssl_cert" "$ssl_key" "$https_port" "$http_port")"
  nginx_install_site "$conf" "$domain"
}

nginx_default_deny_basename() {
  printf '%s' "00-adminpanelaz-default-deny"
}

nginx_version_at_least() {
  local want="$1" version_output="$2" have
  have="$(printf '%s' "$version_output" | sed -n 's|.*nginx/\([0-9][0-9.]*\).*|\1|p' | head -1)"
  [[ -n "$have" ]] || return 1
  [[ "$(printf '%s\n%s\n' "$want" "$have" | sort -V | head -1)" == "$want" ]]
}

# nginx_render_default_deny <HTTP listen через пробел|""> <HTTPS listen через пробел|""> <вывод nginx -v>
nginx_render_default_deny() {
  local http_listens="$1" https_listens="$2" version_output="$3" listen
  printf '# AdminPanelAZ: запросы по IP сервера и к чужим именам не доходят до панели.\n'
  if [[ -n "$http_listens" ]]; then
    printf 'server {\n'
    for listen in $http_listens; do
      printf '    listen %s default_server;\n' "$listen"
    done
    printf '    server_name _;\n    return 444;\n}\n'
  fi
  if [[ -n "$https_listens" ]]; then
    printf 'server {\n'
    for listen in $https_listens; do
      printf '    listen %s ssl default_server;\n' "$listen"
    done
    printf '    server_name _;\n'
    if nginx_version_at_least 1.19.4 "$version_output"; then
      printf '    ssl_reject_handshake on;\n'
    else
      printf '    ssl_certificate %s;\n    ssl_certificate_key %s;\n    return 444;\n' \
        "$(nginx_default_deny_cert)" "$(nginx_default_deny_key)"
    fi
    printf '}\n'
  fi
}

nginx_default_deny_cert() {
  printf '%s' "${NGINX_DEFAULT_DENY_CERT:-/etc/ssl/certs/adminpanelaz-default-deny.crt}"
}

nginx_default_deny_key() {
  printf '%s' "${NGINX_DEFAULT_DENY_KEY:-/etc/ssl/private/adminpanelaz-default-deny.key}"
}

nginx_ensure_default_deny_cert() {
  local cert key
  cert="$(nginx_default_deny_cert)"
  key="$(nginx_default_deny_key)"
  [[ -s "$cert" && -s "$key" ]] && return 0
  mkdir -p "$(dirname "$cert")" "$(dirname "$key")"
  (umask 077 && openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -subj "/CN=invalid" \
    -keyout "$key" -out "$cert" >/dev/null 2>&1)
}

# Файлы конфигурации в порядке загрузки: по nginx -T, иначе как в nginx.conf Debian — conf.d, затем sites-enabled.
nginx_loaded_conf_files() {
  local files path
  files="$(nginx -T 2>/dev/null | sed -n 's/^# configuration file \(.*\):$/\1/p' || true)"
  if [[ -z "$files" ]]; then
    files="$(printf '%s\n' "$(nginx_conf_d_dir)"/*.conf "$(nginx_sites_enabled_dir)"/*)"
  fi
  while IFS= read -r path; do
    [[ -f "$path" ]] && printf '%s\n' "$path"
  done <<<"$files"
  return 0
}

# nginx_conf_listens <файл> → «порт ssl|plain default|- адрес» на каждую директиву listen.
nginx_conf_listens() {
  sed 's/#.*//' "$1" | tr ';{}' '\n\n\n' | awk '
    $1 == "listen" {
      addr = $2
      port = addr
      sub(/.*:/, "", port)
      if (port !~ /^[0-9]+$/) next
      ssl = "plain"; def = "-"
      for (i = 3; i <= NF; i++) {
        if ($i == "ssl") ssl = "ssl"
        if ($i == "default_server" || $i == "default") def = "default"
      }
      print port, ssl, def, addr
    }'
}

# IP в server_name: клиент по IP не шлёт SNI, TLS-рукопожатие достаётся серверу по умолчанию.
nginx_conf_has_ip_server_name() {
  sed 's/#.*//' "$1" | tr ';{}' '\n\n\n' | awk '
    $1 == "server_name" {
      for (i = 2; i <= NF; i++)
        if ($i ~ /^[0-9]+(\.[0-9]+)+$/ || $i ~ /^\[?[0-9a-fA-F]*:[0-9a-fA-F:.]*\]?$/) found = 1
    }
    END { exit !found }'
}

# Файл панели или портала: шаблоны начинаются с «# AdminPanelAZ»; только что записанный vhost — тоже свой.
nginx_conf_is_panel_owned() {
  local path="$1"
  [[ -n "${NGINX_CONF_FILE:-}" && "$(basename "$path")" == "$(basename "$NGINX_CONF_FILE")" ]] && return 0
  head -n 1 "$path" 2>/dev/null | grep -q '^#.*AdminPanelAZ'
}

nginx_remove_default_deny() {
  local base
  base="$(nginx_default_deny_basename)"
  rm -f "$(nginx_sites_enabled_dir)/${base}" "$(nginx_sites_available_dir)/${base}"
}

# Без сервера по умолчанию nginx отдаёт запросы по голому IP первому vhost'у на порту.
# Сервер по умолчанию ставится только на порты, где этот первый vhost — панель или портал:
# иначе по IP и так отвечает чужой сайт, и менять его поведение нельзя.
# Ошибка здесь не должна ломать публикацию: default-deny откатывается, панель остаётся.
nginx_install_default_deny() {
  local base conf_file enabled_link version_output conf path owned has_ip
  local port kind def addr http_listens="" https_listens=""
  local -A first=() has_default=() our_kind=() our_ip=() listens=() seen=()
  base="$(nginx_default_deny_basename)"
  conf_file="$(nginx_sites_available_dir)/${base}"
  enabled_link="$(nginx_sites_enabled_dir)/${base}"

  while IFS= read -r path; do
    [[ "$(basename "$path")" == "$base" ]] && continue
    owned=false
    has_ip=false
    if nginx_conf_is_panel_owned "$path"; then
      owned=true
      nginx_conf_has_ip_server_name "$path" && has_ip=true
    fi
    while read -r port kind def addr; do
      [[ -n "${first[$port]:-}" ]] || first[$port]="$owned"
      [[ "$def" == default ]] && has_default[$port]=1
      [[ "$owned" == true ]] || continue
      our_kind[$port]="$kind"
      [[ "$has_ip" == true ]] && our_ip[$port]=1
      if [[ -z "${seen[$addr]:-}" ]]; then
        seen[$addr]=1
        listens[$port]+="${listens[$port]:+ }${addr}"
      fi
    done < <(nginx_conf_listens "$path")
  done < <(nginx_loaded_conf_files)

  while read -r port; do
    [[ -n "$port" ]] || continue
    if [[ -n "${has_default[$port]:-}" ]]; then
      nginx_warn "На порту ${port} уже есть default_server — сервер по умолчанию панели не ставится"
    elif [[ "${first[$port]}" != true ]]; then
      nginx_log "Порт ${port}: первым объявлен чужой сайт — он отвечает по IP, сервер по умолчанию не ставится"
    elif [[ "${our_kind[$port]}" == ssl && -n "${our_ip[$port]:-}" ]]; then
      nginx_log "Порт ${port}: панель открывается по IP — HTTPS-сервер по умолчанию не ставится"
    elif [[ "${our_kind[$port]}" == ssl ]]; then
      https_listens+="${https_listens:+ }${listens[$port]}"
    else
      http_listens+="${http_listens:+ }${listens[$port]}"
    fi
  done < <(printf '%s\n' "${!our_kind[@]}" | sort -n)

  if [[ -z "$http_listens" && -z "$https_listens" ]]; then
    nginx_remove_default_deny
    return 0
  fi

  version_output="$(nginx -v 2>&1 || true)"
  if [[ -n "$https_listens" ]] && ! nginx_version_at_least 1.19.4 "$version_output"; then
    if ! nginx_ensure_default_deny_cert; then
      nginx_warn "Не удалось создать сертификат для сервера по умолчанию — HTTPS по IP не закрыт"
      https_listens=""
    fi
  fi
  conf="$(nginx_render_default_deny "$http_listens" "$https_listens" "$version_output")"
  if ! printf '%s\n' "$conf" 2>/dev/null >"$conf_file" || ! ln -sf "$conf_file" "$enabled_link"; then
    nginx_remove_default_deny
    nginx_warn "Не удалось записать ${conf_file} — панель может открываться по IP сервера"
    return 0
  fi
  if ! nginx -t >/dev/null 2>&1; then
    nginx_remove_default_deny
    nginx_warn "Сервер по умолчанию не прошёл nginx -t — убран; панель может открываться по IP сервера"
    return 0
  fi
  nginx_log "Запросы по IP сервера и к чужим именам отклоняются (${base})"
}

# Undo a failed install: never leave a broken site enabled (would block nginx after reboot/reload).
nginx_rollback_site_install() {
  local bak="${1:-}"
  local created_enabled="${2:-false}"

  rm -f "$NGINX_ENABLED_LINK"
  if [[ -n "$bak" && -f "$bak" ]]; then
    mv -f "$bak" "$NGINX_CONF_FILE"
    if [[ "$created_enabled" != "true" ]]; then
      ln -sf "$NGINX_CONF_FILE" "$NGINX_ENABLED_LINK"
    fi
  else
    rm -f "$NGINX_CONF_FILE"
  fi
  nginx_rollback_server_names_hash
}

nginx_install_site() {
  local conf_content="$1"
  local domain="$2"
  local reload_only="${3:-false}"
  local bak=""
  local created_enabled=false
  local enabled_dir available_dir

  nginx_ensure_server_names_hash
  nginx_conf_paths "$domain"
  available_dir="$(nginx_sites_available_dir)"
  enabled_dir="$(nginx_sites_enabled_dir)"
  mkdir -p "$available_dir" "$enabled_dir"

  if [[ -f "$NGINX_CONF_FILE" ]]; then
    bak="${NGINX_CONF_FILE}.apaz-install.bak.$$"
    cp -a "$NGINX_CONF_FILE" "$bak"
  fi
  if [[ ! -e "$NGINX_ENABLED_LINK" && ! -L "$NGINX_ENABLED_LINK" ]]; then
    created_enabled=true
  fi

  printf '%s\n' "$conf_content" >"$NGINX_CONF_FILE"
  ln -sf "$NGINX_CONF_FILE" "$NGINX_ENABLED_LINK"
  # Стандартный default мешает: на корне домена показывается «Welcome to nginx».
  rm -f "${enabled_dir}/default"

  if ! nginx -t; then
    nginx_rollback_site_install "$bak" "$created_enabled"
    nginx_die "nginx -t не прошёл (конфиг: $NGINX_CONF_FILE) — изменения откатаны"
  fi
  [[ -n "$bak" && -f "$bak" ]] && rm -f "$bak"
  nginx_cleanup_server_names_hash_bak
  nginx_install_default_deny

  systemctl enable nginx >/dev/null 2>&1 || true
  # Config already passed nginx -t — leave it enabled even if reload/restart fails
  # (operators can start nginx later; do not re-introduce a stale/missing vhost).
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

PORT80_NAT_RULES=()

# Правила NAT PREROUTING для порта 80 на внешнем интерфейсе перехватили бы запросы
# Let's Encrypt к certbot standalone. Снимаются и возвращаются только они, одной транзакцией
# iptables-restore --noflush: полный откат снимка iptables стёр бы правила, добавленные
# за время certbot (fail2ban, VPN, docker). Элемент PORT80_NAT_RULES: "<позиция> <правило>".
nginx_temp_clear_port80_nat() {
  PORT80_NAT_RULES=()
  command -v iptables >/dev/null 2>&1 || return 0
  local iface line entry pos=0
  iface="$(ip route 2>/dev/null | awk '$1 == "default" {for (i = 2; i < NF; i++) if ($i == "dev") {print $(i + 1); exit}}')"
  [[ -n "$iface" ]] || return 0
  while IFS= read -r line; do
    [[ "$line" == "-A PREROUTING "* ]] || continue
    pos=$((pos + 1))
    [[ " $line " == *" -i ${iface} "* && " $line " == *" -p tcp "* && " $line " == *" --dport 80 "* ]] || continue
    PORT80_NAT_RULES+=("${pos} ${line#-A PREROUTING }")
  done < <(iptables -t nat -S PREROUTING 2>/dev/null)
  ((${#PORT80_NAT_RULES[@]} > 0)) || return 0
  if ! {
    echo "*nat"
    for entry in "${PORT80_NAT_RULES[@]}"; do
      echo "-D PREROUTING ${entry#* }"
    done
    echo "COMMIT"
  } | iptables-restore --noflush; then
    nginx_warn "Не удалось снять правила NAT для порта 80 — certbot может не пройти проверку"
    PORT80_NAT_RULES=()
    return 0
  fi
  nginx_log "Временно сняты правила NAT для порта 80: ${#PORT80_NAT_RULES[@]}"
}

nginx_restore_port80_nat() {
  ((${#PORT80_NAT_RULES[@]} > 0)) || return 0
  local current entry pos rule len
  local -a lines=()
  current="$(iptables -t nat -S PREROUTING 2>/dev/null || true)"
  len="$(grep -c '^-A PREROUTING ' <<<"$current" || true)"
  for entry in "${PORT80_NAT_RULES[@]}"; do
    pos="${entry%% *}"
    rule="${entry#* }"
    grep -qxF -- "-A PREROUTING ${rule}" <<<"$current" && continue
    ((pos <= len + 1)) || pos=$((len + 1))
    lines+=("-I PREROUTING ${pos} ${rule}")
    len=$((len + 1))
  done
  if ((${#lines[@]} > 0)) && ! printf '*nat\n%s\nCOMMIT\n' "$(printf '%s\n' "${lines[@]}")" | iptables-restore --noflush; then
    nginx_warn "Не удалось вернуть правила NAT для порта 80. Верните их вручную:"
    for entry in "${PORT80_NAT_RULES[@]}"; do
      nginx_warn "  iptables -t nat -A PREROUTING ${entry#* }"
    done
    PORT80_NAT_RULES=()
    return 1
  fi
  PORT80_NAT_RULES=()
  nginx_log "Правила NAT для порта 80 возвращены"
}

# nginx_certbot_standalone <HTTP-порт ACME> <аргументы certbot> — остановить nginx и выполнить
# certbot без NAT порта 80. При прерывании (bash выполняет EXIT-trap и при SIGINT/SIGTERM)
# правила возвращаются, а остановленный здесь nginx запускается, иначе сервер остался бы без
# сайтов и перенаправления порта 80. Прежний EXIT-trap выполняется следом и восстанавливается.
# После certbot nginx запускает вызывающий код.
nginx_certbot_standalone() {
  local http_port="$1" prev_exit rc=0
  local -a prev=()
  shift
  prev_exit="$(trap -p EXIT)"
  [[ -z "$prev_exit" ]] || eval "prev=(${prev_exit})"
  NGINX_PREV_EXIT_TRAP="${prev[2]:-}"
  NGINX_STOPPED_FOR_ACME=false
  trap 'nginx_restore_port80_nat || true
    [[ "$NGINX_STOPPED_FOR_ACME" != true ]] || systemctl start nginx >/dev/null 2>&1 || true
    eval "$NGINX_PREV_EXIT_TRAP"' EXIT

  nginx_stop_for_standalone_acme "$http_port"
  nginx_temp_clear_port80_nat
  certbot "$@" || rc=$?
  nginx_restore_port80_nat || true

  eval "${prev_exit:-trap - EXIT}"
  return "$rc"
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
  local http_acme_port
  http_acme_port="${HTTP_ACME_PORT:-$(nginx_env_get HTTP_ACME_PORT)}"
  http_acme_port="${http_acme_port:-80}"

  if systemctl is-active nginx >/dev/null 2>&1; then
    nginx_install_temp_acme_http_vhost "$domain" "$http_acme_port" || true
    nginx_log "Пробуем certbot webroot (nginx остаётся запущенным)…"
    if [[ -n "$email" ]]; then
      certbot certonly --webroot -w /var/www/html --non-interactive --agree-tos -m "$email" -d "$domain" && certbot_ok=true || true
    else
      certbot certonly --webroot -w /var/www/html --non-interactive --agree-tos --register-unsafely-without-email -d "$domain" && certbot_ok=true || true
    fi
  fi

  if [[ "$certbot_ok" == "true" && -f "$cert_path" ]]; then
    nginx_remove_temp_acme_http_vhost "$domain"
    nginx_log "Сертификат Let's Encrypt получен через webroot"
    return 0
  fi

  nginx_remove_temp_acme_http_vhost "$domain"
  nginx_log "Webroot не сработал — certbot standalone (nginx будет остановлен)…"
  local -a email_args=(--register-unsafely-without-email)
  [[ -z "$email" ]] || email_args=(-m "$email")
  if ! nginx_certbot_standalone "$http_acme_port" certonly --standalone --non-interactive --agree-tos "${email_args[@]}" -d "$domain"; then
    systemctl start nginx 2>/dev/null || true
    if [[ "${NGINX_FAIL_SOFT:-false}" == true ]]; then
      nginx_warn "Не удалось получить сертификат Let's Encrypt"
      return 1
    fi
    nginx_die "Не удалось получить сертификат Let's Encrypt"
  fi

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

# Добавить origin в CORS_ORIGINS (.env), не затирая существующие.
nginx_cors_add_origin() {
  local origin="$1"
  [[ -n "$origin" ]] || return 0
  local current
  current="$(nginx_env_get CORS_ORIGINS)"
  if [[ -z "$current" ]]; then
    nginx_env_set CORS_ORIGINS "$origin"
    return 0
  fi
  case ",${current}," in
    *",${origin},"*) return 0 ;;
  esac
  nginx_env_set CORS_ORIGINS "${current},${origin}"
}

nginx_cors_add_portal_origins() {
  local portal_domain="$1"
  local scheme="${2:-https}"
  local port="${3:-}"
  portal_domain="$(nginx_normalize_host "$portal_domain")"
  [[ -n "$portal_domain" ]] || return 0
  local host="$portal_domain"
  if [[ -n "$port" && "$port" != "443" && "$scheme" == "https" ]]; then
    host="${portal_domain}:${port}"
  elif [[ -n "$port" && "$port" != "80" && "$scheme" == "http" ]]; then
    host="${portal_domain}:${port}"
  fi
  nginx_cors_add_origin "${scheme}://${host}"
  if [[ "$scheme" == "https" ]]; then
    nginx_cors_add_origin "http://${host}"
  fi
}

# 0 = cert covers hostname (CN or SAN).
nginx_cert_covers_host() {
  local cert="$1"
  local host="$2"
  host="$(nginx_normalize_host "$host")"
  [[ -f "$cert" && -n "$host" ]] || return 1
  local text
  text="$(openssl x509 -in "$cert" -noout -text 2>/dev/null)" || return 1
  echo "$text" | grep -Eiq "DNS:${host}(,|$| )" && return 0
  echo "$text" | grep -Eiq "DNS:\\*\\.${host#*.}" && return 0
  local cn
  cn="$(openssl x509 -in "$cert" -noout -subject 2>/dev/null | sed -n 's/.*CN *= *\([^/,]*\).*/\1/p')"
  [[ "$(nginx_normalize_host "$cn")" == "$host" ]]
}

# Let's Encrypt for one or more -d names. First domain is the cert lineage directory name.
nginx_obtain_letsencrypt_cert_hosts() {
  local email="$1"
  shift
  local -a hosts=("$@")
  [[ ${#hosts[@]} -ge 1 ]] || nginx_die "nginx_obtain_letsencrypt_cert_hosts: нет доменов"
  local primary="${hosts[0]}"
  local cert_path="/etc/letsencrypt/live/${primary}/fullchain.pem"
  local -a d_args=()
  local h
  for h in "${hosts[@]}"; do
    h="$(nginx_normalize_host "$h")"
    [[ -n "$h" ]] || continue
    d_args+=(-d "$h")
  done
  [[ ${#d_args[@]} -ge 1 ]] || nginx_die "nginx_obtain_letsencrypt_cert_hosts: пустые домены"

  local need_issue=true
  if [[ -f "$cert_path" ]]; then
    need_issue=false
    for h in "${hosts[@]}"; do
      h="$(nginx_normalize_host "$h")"
      if ! nginx_cert_covers_host "$cert_path" "$h"; then
        need_issue=true
        break
      fi
    done
  fi
  if [[ "$need_issue" != "true" ]]; then
    nginx_log "Сертификат Let's Encrypt уже покрывает (выпуск не нужен): ${hosts[*]}"
    return 0
  fi

  nginx_ensure_certbot || nginx_die "Не удалось установить certbot"
  mkdir -p /var/www/html/.well-known/acme-challenge

  local certbot_ok=false
  local expand_flag=()
  local http_acme_port
  [[ -f "$cert_path" ]] && expand_flag=(--expand)
  http_acme_port="${HTTP_ACME_PORT:-$(nginx_env_get HTTP_ACME_PORT)}"
  http_acme_port="${http_acme_port:-80}"

  if systemctl is-active nginx >/dev/null 2>&1; then
    for h in "${hosts[@]}"; do
      h="$(nginx_normalize_host "$h")"
      [[ -n "$h" ]] || continue
      nginx_install_temp_acme_http_vhost "$h" "$http_acme_port" || true
    done
    nginx_log "certbot webroot для: ${hosts[*]}"
    if [[ -n "$email" ]]; then
      certbot certonly --webroot -w /var/www/html --non-interactive --agree-tos -m "$email" \
        "${expand_flag[@]}" "${d_args[@]}" && certbot_ok=true || true
    else
      certbot certonly --webroot -w /var/www/html --non-interactive --agree-tos --register-unsafely-without-email \
        "${expand_flag[@]}" "${d_args[@]}" && certbot_ok=true || true
    fi
  fi

  if [[ "$certbot_ok" == "true" && -f "$cert_path" ]]; then
    for h in "${hosts[@]}"; do
      nginx_remove_temp_acme_http_vhost "$h"
    done
    nginx_log "Let's Encrypt получен (webroot): ${hosts[*]}"
    return 0
  fi

  for h in "${hosts[@]}"; do
    nginx_remove_temp_acme_http_vhost "$h"
  done

  nginx_log "Webroot не сработал — certbot standalone для: ${hosts[*]}"
  local -a email_args=(--register-unsafely-without-email)
  [[ -z "$email" ]] || email_args=(-m "$email")
  if ! nginx_certbot_standalone "$http_acme_port" certonly --standalone --non-interactive --agree-tos "${email_args[@]}" \
    "${expand_flag[@]}" "${d_args[@]}"; then
    systemctl start nginx 2>/dev/null || true
    nginx_die "Не удалось получить сертификат Let's Encrypt для ${hosts[*]}"
  fi

  systemctl start nginx 2>/dev/null || true
  [[ -f "$cert_path" ]] || nginx_die "Сертификат не найден после certbot: $cert_path"
}

nginx_generate_selfsigned_hosts() {
  local cert_out="$1"
  local key_out="$2"
  shift 2
  local -a hosts=("$@")
  [[ ${#hosts[@]} -ge 1 ]] || nginx_die "nginx_generate_selfsigned_hosts: нет имён"
  local primary="${hosts[0]}"
  mkdir -p "$(dirname "$cert_out")" "$(dirname "$key_out")"
  local san="" h
  for h in "${hosts[@]}"; do
    h="$(nginx_normalize_host "$h")"
    [[ -n "$h" ]] || continue
    if [[ -n "$san" ]]; then
      san="${san},DNS:${h}"
    else
      san="DNS:${h}"
    fi
  done
  local tmp
  tmp="$(mktemp)"
  cat >"$tmp" <<EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no
[req_distinguished_name]
CN = ${primary}
[v3_req]
subjectAltName = ${san}
EOF
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$key_out" -out "$cert_out" \
    -config "$tmp" -extensions v3_req >/dev/null 2>&1 || {
    rm -f "$tmp"
    nginx_die "Не удалось создать самоподписанный сертификат"
  }
  rm -f "$tmp"
  nginx_log "Самоподписанный сертификат: ${hosts[*]} → ${cert_out}"
}

nginx_render_portal_template() {
  local portal_domain="$1"
  local backend_port="$2"
  local ssl_cert="$3"
  local ssl_key="$4"
  local https_port="${5:-443}"
  local http_port="${6:-80}"
  local template https_redirect_suffix portal_blocks rendered
  # Portal subdomain always serves at root (not panel ACCESS_PATH); allowlist only.
  template="$NGINX_TEMPLATE_DIR/adminpanelaz-portal.conf.template"
  nginx_ensure_cloudflare_realip_snippet
  nginx_ensure_cloudflare_origin_snippets
  https_redirect_suffix="$(nginx_https_redirect_suffix "$https_port")"
  portal_blocks="$(nginx_portal_location_blocks "$backend_port")"
  rendered="$(sed \
    -e "s|__DOMAIN__|${portal_domain}|g" \
    -e "s|__BACKEND_PORT__|${backend_port}|g" \
    -e "s|__HTTPS_PORT__|${https_port}|g" \
    -e "s|__HTTPS_REDIRECT_SUFFIX__|${https_redirect_suffix}|g" \
    -e "s|__HTTP_PORT__|${http_port}|g" \
    -e "s|__SSL_CERT__|${ssl_cert}|g" \
    -e "s|__SSL_KEY__|${ssl_key}|g" \
    -e "s|__UVICORN_PORT__|${backend_port}|g" \
    "$template")"
  PANEL_BLOCKS="$portal_blocks" RENDERED="$rendered" python3 - <<'PY'
import os
print(os.environ["RENDERED"].replace("__PANEL_LOCATION_BLOCKS__", os.environ["PANEL_BLOCKS"]), end="")
PY
}

nginx_install_portal_vhost() {
  local portal_domain="$1"
  local backend_port="$2"
  local ssl_cert="$3"
  local ssl_key="$4"
  local https_port="${5:-443}"
  local http_port="${6:-80}"
  local conf
  conf="$(nginx_render_portal_template "$portal_domain" "$backend_port" "$ssl_cert" "$ssl_key" "$https_port" "$http_port")"
  nginx_install_site "$conf" "$portal_domain" "true"
}

# Main entry: provision portal host for current PUBLISH_MODE.
# Env: PORTAL_DOMAIN (required), DOMAIN, EMAIL, BACKEND_PORT, HTTPS_PUBLIC_PORT, HTTP_ACME_PORT, SSL_CERT, SSL_KEY
nginx_provision_portal_domain() {
  local portal_domain
  portal_domain="$(nginx_normalize_host "${1:-${PORTAL_DOMAIN:-}}")"
  [[ -n "$portal_domain" ]] || nginx_die "PORTAL_DOMAIN не задан"

  local panel_domain
  panel_domain="$(nginx_normalize_host "$(nginx_env_get DOMAIN)")"
  [[ -z "$panel_domain" ]] && panel_domain="$(nginx_normalize_host "${DOMAIN:-}")"

  if [[ -n "$panel_domain" && "$portal_domain" == "$panel_domain" ]]; then
    nginx_die "Хост портала не должен совпадать с доменом панели (${panel_domain})"
  fi
  nginx_assert_domain_not_az_vpn_host "$portal_domain"

  local mode
  mode="${PUBLISH_MODE:-}"
  if [[ -z "$mode" ]]; then
    mode="$(nginx_env_get PUBLISH_MODE)"
  fi
  mode="${mode:-}"
  local backend_port https_port http_port email
  backend_port="${BACKEND_PORT:-$(nginx_env_get BACKEND_PORT)}"
  backend_port="${backend_port:-8000}"
  https_port="${HTTPS_PUBLIC_PORT:-$(nginx_env_get HTTPS_PUBLIC_PORT)}"
  https_port="${https_port:-443}"
  http_port="${HTTP_ACME_PORT:-$(nginx_env_get HTTP_ACME_PORT)}"
  http_port="${http_port:-80}"
  email="${EMAIL:-}"

  local ssl_cert ssl_key
  ssl_cert="${SSL_CERT:-$(nginx_env_get SSL_CERT)}"
  ssl_key="${SSL_KEY:-$(nginx_env_get SSL_KEY)}"

  case "$mode" in
    nginx_le)
      nginx_ensure_nginx || nginx_die "Не удалось установить nginx"
      nginx_obtain_letsencrypt_cert_hosts "$email" "$portal_domain"
      ssl_cert="/etc/letsencrypt/live/${portal_domain}/fullchain.pem"
      ssl_key="/etc/letsencrypt/live/${portal_domain}/privkey.pem"
      nginx_install_portal_vhost "$portal_domain" "$backend_port" "$ssl_cert" "$ssl_key" "$https_port" "$http_port"
      nginx_cors_add_portal_origins "$portal_domain" "https" "$https_port"
      ;;
    nginx_selfsigned)
      nginx_ensure_nginx || nginx_die "Не удалось установить nginx"
      if [[ -n "$panel_domain" ]]; then
        nginx_generate_selfsigned_hosts "$NGINX_SELF_SIGNED_CERT" "$NGINX_SELF_SIGNED_KEY" "$panel_domain" "$portal_domain"
      else
        nginx_generate_selfsigned_hosts "$NGINX_SELF_SIGNED_CERT" "$NGINX_SELF_SIGNED_KEY" "$portal_domain"
      fi
      nginx_install_portal_vhost "$portal_domain" "$backend_port" \
        "$NGINX_SELF_SIGNED_CERT" "$NGINX_SELF_SIGNED_KEY" "$https_port" "$http_port"
      nginx_cors_add_portal_origins "$portal_domain" "https" "$https_port"
      ;;
    nginx_custom)
      nginx_ensure_nginx || nginx_die "Не удалось установить nginx"
      [[ -n "$ssl_cert" && -n "$ssl_key" ]] || nginx_die "Для nginx_custom нужны SSL_CERT и SSL_KEY"
      [[ -f "$ssl_cert" && -f "$ssl_key" ]] || nginx_die "Файлы сертификата не найдены: $ssl_cert / $ssl_key"
      if ! nginx_cert_covers_host "$ssl_cert" "$portal_domain"; then
        nginx_die "Сертификат не покрывает хост портала ${portal_domain}. Добавьте SAN или укажите другой cert."
      fi
      nginx_install_portal_vhost "$portal_domain" "$backend_port" "$ssl_cert" "$ssl_key" "$https_port" "$http_port"
      nginx_cors_add_portal_origins "$portal_domain" "https" "$https_port"
      ;;
    uvicorn_le)
      [[ -n "$panel_domain" ]] || nginx_die "DOMAIN панели обязателен для uvicorn_le + портал"
      nginx_obtain_letsencrypt_cert_hosts "$email" "$panel_domain" "$portal_domain"
      ssl_cert="/etc/letsencrypt/live/${panel_domain}/fullchain.pem"
      ssl_key="/etc/letsencrypt/live/${panel_domain}/privkey.pem"
      nginx_env_set SSL_CERT "$ssl_cert"
      nginx_env_set SSL_KEY "$ssl_key"
      nginx_cors_add_portal_origins "$portal_domain" "https" "$backend_port"
      nginx_log "SAN-сертификат обновлён для uvicorn; перезапустите панель"
      ;;
    uvicorn_selfsigned)
      local names=()
      [[ -n "$panel_domain" ]] && names+=("$panel_domain")
      names+=("$portal_domain")
      nginx_generate_selfsigned_hosts "$NGINX_SELF_SIGNED_CERT" "$NGINX_SELF_SIGNED_KEY" "${names[@]}"
      nginx_env_set SSL_CERT "$NGINX_SELF_SIGNED_CERT"
      nginx_env_set SSL_KEY "$NGINX_SELF_SIGNED_KEY"
      nginx_cors_add_portal_origins "$portal_domain" "https" "$backend_port"
      ;;
    uvicorn_custom)
      [[ -n "$ssl_cert" && -n "$ssl_key" ]] || nginx_die "Для uvicorn_custom нужны SSL_CERT и SSL_KEY"
      [[ -f "$ssl_cert" && -f "$ssl_key" ]] || nginx_die "Файлы сертификата не найдены"
      if ! nginx_cert_covers_host "$ssl_cert" "$portal_domain"; then
        nginx_die "Сертификат не покрывает хост портала ${portal_domain}. Добавьте SAN."
      fi
      nginx_cors_add_portal_origins "$portal_domain" "https" "$backend_port"
      ;;
    http_direct|"")
      if [[ -z "$mode" || "$mode" == "http_direct" ]]; then
        nginx_cors_add_portal_origins "$portal_domain" "http" "$backend_port"
        nginx_warn "Режим http_direct: TLS не настраивается. Портал: http://${portal_domain}:${backend_port}/p/…"
      else
        nginx_die "Неизвестный PUBLISH_MODE=${mode}"
      fi
      ;;
    *)
      nginx_die "Неподдерживаемый PUBLISH_MODE для портала: ${mode:-<пусто>}"
      ;;
  esac

  nginx_env_set PORTAL_DOMAIN "$portal_domain"
  local access_url
  if [[ "$mode" == "http_direct" || -z "$mode" ]]; then
    access_url="http://${portal_domain}:${backend_port}/"
  elif [[ "$mode" == uvicorn_le || "$mode" == uvicorn_selfsigned || "$mode" == uvicorn_custom ]]; then
    access_url="https://${portal_domain}:${backend_port}/"
  elif [[ "$https_port" != "443" ]]; then
    access_url="https://${portal_domain}:${https_port}/"
  else
    access_url="https://${portal_domain}/"
  fi
  echo "PORTAL_ACCESS_URL=${access_url}"
  nginx_log "Портал настроен: ${portal_domain} (режим ${mode:-http_direct})"
}
