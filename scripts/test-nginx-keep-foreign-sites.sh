#!/usr/bin/env bash
# Переход на прямую публикацию останавливает nginx, только если на нём нет чужих сайтов:
# сайты бывают не только в sites-enabled, но и в conf.d и в любых include.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ENV_FILE="$TMP/.env"
: >"$ENV_FILE"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init
set +e

export NGINX_SITES_AVAILABLE_DIR="$TMP/sites-available"
export NGINX_SITES_ENABLED_DIR="$TMP/sites-enabled"
export NGINX_CONF_D_DIR="$TMP/conf.d"
ENABLED="$NGINX_SITES_ENABLED_DIR"
CONFD="$NGINX_CONF_D_DIR"
EXTRA="$TMP/vhosts"
MAIN="$TMP/nginx.conf"

# Функции перекрывают настоящие nginx/systemctl: тест не трогает nginx сервера.
FAKE_DUMP=1
nginx() {
  case "${1:-}" in
    -T)
      [[ "$FAKE_DUMP" == 1 ]] || return 1
      local f
      for f in "$MAIN" "$ENABLED"/* "$CONFD"/*.conf "$EXTRA"/*.conf; do
        [[ -f "$f" ]] || continue
        echo "# configuration file $f:"
        cat "$f"
        echo
      done
      ;;
    *) return 0 ;;
  esac
}
systemctl() { echo "systemctl $*" >>"$TMP/systemctl.log"; }

reset() {
  rm -rf "$ENABLED" "$CONFD" "$EXTRA" "$NGINX_SITES_AVAILABLE_DIR"
  mkdir -p "$ENABLED" "$CONFD" "$EXTRA" "$NGINX_SITES_AVAILABLE_DIR"
  printf 'events {}\nhttp {\n  include %s/*;\n  include %s/*.conf;\n  #server { listen 81; }\n}\n' "$ENABLED" "$CONFD" >"$MAIN"
  : >"$TMP/systemctl.log"
  FAKE_DUMP=1
  # Файлы самой панели и стандартная заглушка не считаются чужими сайтами.
  printf 'server { listen 443 ssl; server_name panel.example.com; }\n' >"$ENABLED/panel_example_com"
  printf 'server { listen 80 default_server; return 444; }\n' >"$ENABLED/00-adminpanelaz-default-deny"
  printf 'server { listen 80; server_name panel.example.com; }\n' >"$ENABLED/adminpanelaz-acme-panel_example_com"
  printf 'server { listen 80 default_server; root /var/www/html; }\n' >"$ENABLED/default"
  printf 'server { listen 80; server_name localhost; }\n' >"$CONFD/default.conf"
  printf 'geo $adminpanelaz_cf { default 0; }\n' >"$CONFD/adminpanelaz-cloudflare-origin.conf"
  printf 'server_names_hash_bucket_size 128;\n' >"$CONFD/adminpanelaz-server-names-hash.conf"
}

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

count() { nginx_count_other_enabled_sites panel.example.com; }

echo "[test] только файлы панели — чужих сайтов нет"
reset
[[ "$(count)" == 0 ]] || fail "насчитано $(count)"
printf 'upstream app { server 127.0.0.1:3000; }\n' >"$CONFD/upstream.conf"
printf '# server {\n#   listen 8081;\n# }\n' >"$CONFD/commented.conf"
[[ "$(count)" == 0 ]] || fail "upstream или закомментированный server посчитан сайтом: $(count)"
echo "  OK"

echo "[test] сайт в conf.d считается"
reset
printf 'server {\n  listen 80;\n  server_name shop.example;\n}\n' >"$CONFD/shop.conf"
[[ "$(count)" == 1 ]] || fail "conf.d: $(count)"
echo "  OK"

echo "[test] сайт из стороннего include считается"
reset
printf 'server\n{\n  server_name blog.example;\n}\n' >"$EXTRA/blog.conf"
[[ "$(count)" == 1 ]] || fail "include без listen и со скобкой на новой строке: $(count)"
echo "  OK"

echo "[test] без nginx -T — sites-enabled и conf.d"
reset
FAKE_DUMP=0
printf 'server { listen 80; server_name shop.example; }\n' >"$CONFD/shop.conf"
printf 'server { listen 80; server_name wiki.example; }\n' >"$ENABLED/wiki"
[[ "$(count)" == 2 ]] || fail "запасной путь: $(count)"
echo "  OK"

echo "[test] прямая публикация не останавливает nginx с сайтом в conf.d"
reset
printf 'server { listen 80; server_name shop.example; }\n' >"$CONFD/shop.conf"
( nginx_disable_for_direct_publish panel.example.com ) >/dev/null 2>&1
! grep -q "systemctl stop nginx" "$TMP/systemctl.log" || fail "nginx остановлен при чужом сайте"
[[ ! -e "$ENABLED/panel_example_com" ]] || fail "vhost панели не удалён"
reset
( nginx_disable_for_direct_publish panel.example.com ) >/dev/null 2>&1
grep -q "systemctl stop nginx" "$TMP/systemctl.log" || fail "без чужих сайтов nginx должен останавливаться"
echo "  OK"

echo "All nginx foreign-site checks passed."
