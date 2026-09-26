#!/usr/bin/env bash
# uninstall --remove-nginx удаляет vhost панели, но vhost портала (и vhost других доменов панели, чужие сайты)
# могут подключать общие snippets Cloudflare: без них nginx не поднимется при следующем перезапуске.
# Проверки передаются в check строкой и раскрываются через eval.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

extract() {
  local file="$1" fn
  shift
  for fn in "$@"; do
    sed -n "/^${fn}() {/,/^}/p" "$file"
  done
}

UNINSTALL_FNS="$(extract "$ROOT_DIR/scripts/uninstall.sh" \
  nginx_conf_users remove_nginx_shared_file_unless_used remove_nginx_site_if_present)"
UNINSTALL_FNS_NO_DEFAULTS="${UNINSTALL_FNS//:-\/etc\//}"
if [[ "$UNINSTALL_FNS" != *NGINX_DIR* || "$UNINSTALL_FNS" != *SSL_DIR* || "$UNINSTALL_FNS_NO_DEFAULTS" == *"/etc/"* ]]; then
  echo "  FAIL remove_nginx_site_if_present пишет в /etc напрямую — тест не запускается, чтобы не тронуть сервер" >&2
  exit 1
fi

NGX="$TMP/nginx"
SSL="$TMP/ssl"
FAKE_ROOT="$TMP/root"
mkdir -p "$FAKE_ROOT/backend"
printf 'DOMAIN=panel.example.com\n' >"$FAKE_ROOT/backend/.env"
REAL_NGINX="$(command -v nginx || true)"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }
check() { if eval "$1"; then ok "$2"; else bad "$2"; fi; }

reset() {
  rm -rf "$NGX" "$SSL" "$TMP/systemctl.log" "$TMP/out.log"
  mkdir -p "$NGX"/{sites-available,sites-enabled,snippets,conf.d,backups} "$SSL"/{certs,private}
  cp "$ROOT_DIR/deploy/nginx/cloudflare-realip.conf" "$ROOT_DIR/deploy/nginx/cloudflare-origin-lock.conf" \
    "$ROOT_DIR/deploy/nginx/cloudflare-origin-allow.conf" "$NGX/snippets/"
  printf '# AdminPanelAZ — generated from snippets/cloudflare-origin-allow.conf; do not edit.\ngeo $realip_remote_addr $adminpanelaz_cf_origin {\n    default 0;\n    127.0.0.1 1;\n}\n' \
    >"$NGX/conf.d/adminpanelaz-cloudflare-origin.conf"
  touch "$SSL/certs/adminpanelaz.crt" "$SSL/private/adminpanelaz.key" \
    "$SSL/certs/adminpanelaz-default-deny.crt" "$SSL/private/adminpanelaz-default-deny.key"
  site panel_example_com panel.example.com 18510 realip lock
  site 00-adminpanelaz-default-deny _ 18511
  printf 'server { listen 127.0.0.1:18512; server_name old.example; include snippets/cloudflare-realip.conf; }\n' \
    >"$NGX/backups/old.example.repair.bak"
  NGINX_T_RC=0
}

# site <файл> <server_name> <порт> [realip] [lock]: включённый vhost, подключающий snippets Cloudflare
site() {
  local name="$1" host="$2" port="$3" inc="" arg
  shift 3
  for arg in "$@"; do
    case "$arg" in
      realip) inc+='        include snippets/cloudflare-realip.conf;\n' ;;
      lock) inc+='        include snippets/cloudflare-origin-lock.conf;\n' ;;
    esac
  done
  # shellcheck disable=SC2059
  printf "# AdminPanelAZ — vhost\nserver {\n    listen 127.0.0.1:${port};\n    server_name ${host};\n    location / {\n${inc}        return 200 \"${host}\";\n    }\n}\n" \
    >"$NGX/sites-available/$name"
  ln -sf "$NGX/sites-available/$name" "$NGX/sites-enabled/$name"
}

run_uninstall() {
  NGINX_DIR="$NGX" SSL_DIR="$SSL" ROOT_DIR="$FAKE_ROOT" NGINX_T_RC="$NGINX_T_RC" TMP="$TMP" bash -c '
    set -euo pipefail
    log() { echo "LOG $*"; }
    warn() { echo "WARN $*"; }
    nginx() {
      echo "nginx $*" >>"$TMP/systemctl.log"
      return "$NGINX_T_RC"
    }
    systemctl() {
      local realip=absent
      [[ -f "$NGINX_DIR/snippets/cloudflare-realip.conf" ]] && realip=present
      echo "systemctl $* realip=$realip" >>"$TMP/systemctl.log"
    }
    REMOVE_NGINX=true
    eval "$1"
    remove_nginx_site_if_present
  ' bash "$UNINSTALL_FNS" >"$TMP/out.log" 2>&1
}

# live_nginx_ok: настоящий nginx со своим префиксом принимает то, что осталось после удаления
live_nginx_ok() {
  [[ -n "$REAL_NGINX" ]] || return 0
  printf 'pid %s/nginx.pid;\nerror_log %s/error.log;\nevents {}\nhttp {\n  access_log off;\n  include %s/conf.d/*.conf;\n  include %s/sites-enabled/*;\n}\n' \
    "$NGX" "$NGX" "$NGX" "$NGX" >"$NGX/nginx.conf"
  "$REAL_NGINX" -t -q -p "$NGX/" -c "$NGX/nginx.conf" 2>"$TMP/nginx-t.err" && return 0
  cat "$TMP/nginx-t.err" >&2
  return 1
}

echo "[test] только vhost панели: удаляются vhost, default-deny, сертификаты и все файлы Cloudflare"
reset
printf 'server { listen 127.0.0.1:18513; server_name other.example;\n    # include snippets/cloudflare-realip.conf;\n}\n' >"$NGX/sites-available/other"
ln -s "$NGX/sites-available/other" "$NGX/sites-enabled/other"
run_uninstall
check '[[ ! -e "$NGX/sites-available/panel_example_com" && ! -L "$NGX/sites-enabled/panel_example_com" ]]' "vhost панели удалён"
check '[[ ! -e "$NGX/sites-available/00-adminpanelaz-default-deny" && ! -L "$NGX/sites-enabled/00-adminpanelaz-default-deny" ]]' "default-deny удалён"
check '[[ -z "$(find "$SSL" -type f)" ]]' "сертификаты панели и default-deny удалены"
for f in snippets/cloudflare-realip.conf snippets/cloudflare-origin-lock.conf snippets/cloudflare-origin-allow.conf \
  conf.d/adminpanelaz-cloudflare-origin.conf; do
  check "[[ ! -e \"\$NGX/$f\" ]]" "$f удалён: подключение в комментарии и в backups не считается"
done
check '[[ -f "$NGX/sites-available/other" ]]' "чужой сайт не тронут"
check 'grep -q "^nginx -t" "$TMP/systemctl.log"' "nginx проверен"
check '[[ "$(grep -c "systemctl reload nginx" "$TMP/systemctl.log")" == 1 ]]' "nginx перезагружен один раз"
check 'grep -q "systemctl reload nginx realip=absent" "$TMP/systemctl.log"' "перезагрузка — после удаления snippets"
check 'live_nginx_ok' "настоящий nginx принимает оставшуюся конфигурацию"

echo "[test] vhost портала подключает realip и origin lock: они, geo и allow остаются"
reset
site portal_example_com portal.example.com 18514 realip lock
run_uninstall
check '[[ ! -e "$NGX/sites-available/panel_example_com" ]]' "vhost панели удалён"
check '[[ -L "$NGX/sites-enabled/portal_example_com" ]]' "vhost портала не тронут"
for f in snippets/cloudflare-realip.conf snippets/cloudflare-origin-lock.conf snippets/cloudflare-origin-allow.conf \
  conf.d/adminpanelaz-cloudflare-origin.conf; do
  check "[[ -f \"\$NGX/$f\" ]]" "$f оставлен"
done
check 'grep -q "WARN snippet Cloudflare realip .* оставлен, его использует: .*portal_example_com" "$TMP/out.log"' "предупреждение называет vhost портала"
check 'grep -q "systemctl reload nginx realip=present" "$TMP/systemctl.log"' "nginx перезагружен с оставшимся snippet"
check 'live_nginx_ok' "настоящий nginx принимает конфигурацию с порталом"

echo "[test] портал без origin lock: realip остаётся, lock, geo и allow удаляются"
reset
site portal_example_com portal.example.com 18514 realip
run_uninstall
check '[[ -f "$NGX/snippets/cloudflare-realip.conf" ]]' "realip оставлен"
check '[[ ! -e "$NGX/snippets/cloudflare-origin-lock.conf" ]]' "lock удалён"
check '[[ ! -e "$NGX/conf.d/adminpanelaz-cloudflare-origin.conf" ]]' "geo удалён: его использовал только lock"
check '[[ ! -e "$NGX/snippets/cloudflare-origin-allow.conf" ]]' "allow удалён вместе с geo"
check 'live_nginx_ok' "настоящий nginx принимает конфигурацию"

echo "[test] чужой сайт использует переменную geo напрямую: geo и allow остаются"
reset
printf 'server {\n    listen 127.0.0.1:18515;\n    server_name own.example;\n    if ($adminpanelaz_cf_origin = 0) { return 403; }\n}\n' \
  >"$NGX/sites-available/own"
ln -s "$NGX/sites-available/own" "$NGX/sites-enabled/own"
run_uninstall
check '[[ ! -e "$NGX/snippets/cloudflare-origin-lock.conf" ]]' "lock удалён"
check '[[ -f "$NGX/conf.d/adminpanelaz-cloudflare-origin.conf" && -f "$NGX/snippets/cloudflare-origin-allow.conf" ]]' "geo и allow оставлены"
check 'live_nginx_ok' "настоящий nginx принимает конфигурацию"

echo "[test] включённый сайт — symlink на файл вне каталога nginx: его подключение учитывается"
reset
mkdir -p "$TMP/srv"
printf 'server { listen 127.0.0.1:18516; server_name srv.example; include snippets/cloudflare-realip.conf; }\n' >"$TMP/srv/site"
ln -s "$TMP/srv/site" "$NGX/sites-enabled/srv"
run_uninstall
check '[[ -f "$NGX/snippets/cloudflare-realip.conf" ]]' "realip оставлен"
check 'live_nginx_ok' "настоящий nginx принимает конфигурацию"

echo "[test] vhost панели уже удалён, остались только snippets: они удаляются, nginx проверяется и перезагружается"
reset
rm -f "$NGX"/sites-*/panel_example_com "$NGX"/sites-*/00-adminpanelaz-default-deny
run_uninstall
check '[[ ! -e "$NGX/snippets/cloudflare-realip.conf" && ! -e "$NGX/conf.d/adminpanelaz-cloudflare-origin.conf" ]]' "snippets и geo удалены"
check 'grep -q "^nginx -t" "$TMP/systemctl.log" && grep -q "systemctl reload nginx" "$TMP/systemctl.log"' "nginx проверен и перезагружен"
rm -f "$TMP/systemctl.log"
run_uninstall
check '[[ ! -e "$TMP/systemctl.log" ]]' "повторный запуск: удалять нечего, nginx не трогается"

echo "[test] nginx -t не прошёл — nginx не перезагружается, выводится предупреждение"
reset
NGINX_T_RC=1
run_uninstall
check '! grep -q "systemctl reload" "$TMP/systemctl.log"' "reload не вызван"
check 'grep -q "WARN nginx -t не прошёл" "$TMP/out.log"' "предупреждение о nginx -t"

echo "[test] без DOMAIN ничего не удаляется"
reset
: >"$FAKE_ROOT/backend/.env"
run_uninstall
check '[[ -f "$NGX/sites-available/panel_example_com" && -f "$NGX/snippets/cloudflare-realip.conf" ]]' "файлы на месте"
check '[[ ! -e "$TMP/systemctl.log" ]]' "nginx не трогается"
printf 'DOMAIN=panel.example.com\n' >"$FAKE_ROOT/backend/.env"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
