#!/usr/bin/env bash
# conf.d/adminpanelaz-cloudflare-origin.conf подключается глобально: если установка сайта
# не прошла nginx -t, geo возвращается к прежнему виду (или удаляется, если его не было).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# Не рабочий backend/.env: библиотека пишет в ENV_FILE.
ENV_FILE="$TMP/.env"
: >"$ENV_FILE"
# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

export NGINX_SNIPPETS_DIR="$TMP/nginx/snippets"
export NGINX_BACKUPS_DIR="$TMP/nginx/backups"
export NGINX_CONF_D_DIR="$TMP/nginx/conf.d"
export NGINX_SITES_AVAILABLE_DIR="$TMP/nginx/sites-available"
export NGINX_SITES_ENABLED_DIR="$TMP/nginx/sites-enabled"
export NGINX_FAIL_FLAG="$TMP/nginx-t-fails"
GEO="$NGINX_CONF_D_DIR/adminpanelaz-cloudflare-origin.conf"
OLD_GEO=$'# old geo\ngeo $realip_remote_addr $adminpanelaz_cf_origin {\n    default 0;\n    192.0.2.0/24 1;\n}\n'
DOMAIN="panel.example.com"

mkdir -p "$TMP/bin"
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "-t" && -f "${NGINX_FAIL_FLAG:?}" ]]; then
  echo "nginx: configuration file test failed" >&2
  exit 1
fi
exit 0
EOF
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/bin/systemctl"
chmod +x "$TMP/bin/nginx" "$TMP/bin/systemctl"
export PATH="$TMP/bin:$PATH"

reset_tree() {
  rm -rf "$TMP/nginx"
  mkdir -p "$NGINX_SNIPPETS_DIR" "$NGINX_BACKUPS_DIR" "$NGINX_CONF_D_DIR" \
    "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR"
  rm -f "$NGINX_FAIL_FLAG"
}

nginx_fails() { : >"$NGINX_FAIL_FLAG"; }

assert_old_geo() {
  if [[ -f "$GEO" && "$(cat "$GEO"; echo x)" == "${OLD_GEO}x" ]]; then
    ok "$1"
  else
    bad "$1: $(cat "$GEO" 2>/dev/null || echo 'файла нет')"
  fi
}

assert_new_geo() {
  if [[ -f "$GEO" ]] && grep -qF 'default 0;' "$GEO" && grep -qF '# AdminPanelAZ — generated' "$GEO"; then
    ok "$1"
  else
    bad "$1: $(cat "$GEO" 2>/dev/null || echo 'файла нет')"
  fi
}

assert_no_pending() {
  local left
  left="$(find "$NGINX_CONF_D_DIR" -name '*.apaz-install.*' -o -name '*.tmp.*')"
  if [[ -z "$left" ]]; then
    ok "$1"
  else
    bad "$1: $left"
  fi
}

run_quiet() {
  set +e
  ( "$@" ) >"$TMP/out" 2>&1
  rc=$?
  set -e
}

echo "[test] выделенный vhost панели: nginx -t не прошёл — прежний geo восстановлен"
reset_tree
printf '%s' "$OLD_GEO" >"$GEO"
nginx_fails
run_quiet nginx_install_dedicated_panel_vhost "$DOMAIN" 8000 /cert.pem /key.pem
[[ "$rc" -ne 0 ]] && ok "установка упала" || bad "установка должна упасть"
assert_old_geo "geo как до установки"
assert_no_pending "в conf.d не осталось временных копий"
if [[ ! -e "$NGINX_SITES_ENABLED_DIR/$(nginx_conf_basename "$DOMAIN")" ]]; then
  ok "сайт не включён"
else
  bad "сайт остался включён"
fi

echo "[test] geo не было: после неудачной установки его нет"
reset_tree
nginx_fails
run_quiet nginx_install_dedicated_panel_vhost "$DOMAIN" 8000 /cert.pem /key.pem
[[ "$rc" -ne 0 ]] && ok "установка упала" || bad "установка должна упасть"
[[ ! -e "$GEO" ]] && ok "созданный geo удалён" || bad "созданный geo остался: $(cat "$GEO")"
assert_no_pending "в conf.d не осталось временных копий"

echo "[test] geo не было: успешная установка создаёт его без временных копий"
reset_tree
run_quiet nginx_install_dedicated_panel_vhost "$DOMAIN" 8000 /cert.pem /key.pem
[[ "$rc" -eq 0 ]] && ok "установка прошла" || bad "установка упала: $(cat "$TMP/out")"
assert_new_geo "geo создан"
assert_no_pending "в conf.d не осталось временных копий"

echo "[test] geo уже актуален: неудачная установка его не трогает"
reset_tree
nginx_render_cloudflare_origin_geo "$NGINX_TEMPLATE_DIR/cloudflare-origin-allow.conf" >"$GEO"
cp -p "$GEO" "$TMP/geo.current"
nginx_fails
run_quiet nginx_install_dedicated_panel_vhost "$DOMAIN" 8000 /cert.pem /key.pem
cmp -s "$GEO" "$TMP/geo.current" && ok "geo прежний" || bad "geo изменился"
assert_no_pending "в conf.d не осталось временных копий"

echo "[test] успешная установка: новый geo, временных копий нет, история в backups"
reset_tree
printf '%s' "$OLD_GEO" >"$GEO"
run_quiet nginx_install_dedicated_panel_vhost "$DOMAIN" 8000 /cert.pem /key.pem
[[ "$rc" -eq 0 ]] && ok "установка прошла" || bad "установка упала: $(cat "$TMP/out")"
assert_new_geo "geo обновлён"
assert_no_pending "в conf.d не осталось временных копий"
if grep -rqF '# old geo' "$NGINX_BACKUPS_DIR"; then
  ok "прежний geo сохранён в backups"
else
  bad "прежнего geo нет в backups"
fi

echo "[test] портал: geo пишется при рендере в подоболочке и тоже откатывается"
reset_tree
printf '%s' "$OLD_GEO" >"$GEO"
nginx_fails
run_quiet nginx_install_portal_vhost "portal.example.com" 8000 /cert.pem /key.pem
[[ "$rc" -ne 0 ]] && ok "установка портала упала" || bad "установка портала должна упасть"
assert_old_geo "geo как до установки портала"
assert_no_pending "в conf.d не осталось временных копий"

echo "[test] geo менялся дважды до nginx -t: откат к состоянию до установки"
reset_tree
printf '%s' "$OLD_GEO" >"$GEO"
run_quiet nginx_ensure_cloudflare_origin_allow_snippet
run_quiet nginx_ensure_cloudflare_origin_geo_conf
printf 'allow 198.51.100.0/24;\n' >>"$NGINX_SNIPPETS_DIR/cloudflare-origin-allow.conf"
run_quiet nginx_ensure_cloudflare_origin_geo_conf
grep -qF '198.51.100.0/24 1;' "$GEO" && ok "второе изменение записано" || bad "второе изменение не записано"
run_quiet nginx_rollback_cloudflare_origin_geo
assert_old_geo "geo как до первого изменения"
assert_no_pending "в conf.d не осталось временных копий"
reset_tree
run_quiet nginx_ensure_cloudflare_origin_allow_snippet
run_quiet nginx_ensure_cloudflare_origin_geo_conf
printf 'allow 198.51.100.0/24;\n' >>"$NGINX_SNIPPETS_DIR/cloudflare-origin-allow.conf"
run_quiet nginx_ensure_cloudflare_origin_geo_conf
run_quiet nginx_rollback_cloudflare_origin_geo
[[ ! -e "$GEO" ]] && ok "geo создан и изменён — после отката его нет" || bad "geo остался: $(cat "$GEO")"
assert_no_pending "в conf.d не осталось временных копий"

echo "[test] subpath (nginx-setup.sh): geo откатывается при неудачном nginx -t и чистится при успехе"
eval "$(sed -n '/^nginx_finalize_nginx_site() {/,/^}/p' "$ROOT_DIR/scripts/nginx-setup.sh")"
declare -F nginx_finalize_nginx_site >/dev/null || bad "nginx_finalize_nginx_site не найдена"
nginx_cleanup_subpath_snippets_for_domain() { :; }
nginx_has_foreign_vhost_for_domain() { return 0; }
nginx_remove_our_dedicated_sites_for_domain() { :; }
nginx_install_subpath_snippet() {
  nginx_ensure_cloudflare_origin_snippets
  NGINX_SUBPATH_SNIPPET_INCLUDE="snippets/test.conf"
}
reset_tree
printf '%s' "$OLD_GEO" >"$GEO"
nginx_fails
ACCESS_PATH=/panel run_quiet nginx_finalize_nginx_site "$DOMAIN" 8000
[[ "$rc" -ne 0 ]] && ok "subpath упал" || bad "subpath должен упасть"
assert_old_geo "geo как до subpath"
assert_no_pending "в conf.d не осталось временных копий"
reset_tree
printf '%s' "$OLD_GEO" >"$GEO"
ACCESS_PATH=/panel run_quiet nginx_finalize_nginx_site "$DOMAIN" 8000
[[ "$rc" -eq 0 ]] && ok "subpath прошёл" || bad "subpath упал: $(cat "$TMP/out")"
assert_new_geo "geo обновлён"
assert_no_pending "в conf.d не осталось временных копий"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
