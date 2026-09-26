#!/usr/bin/env bash
# Неудачный nginx -t при установке сайта: чужой vhost (subpath), snippet панели и общие snippets
# Cloudflare возвращаются к виду до запуска байт-в-байт (права, владелец, симлинки), созданные
# запуском файлы удаляются, nginx не перезагружается. Успешная установка не оставляет копий.
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
export SYSTEMCTL_LOG="$TMP/systemctl.log"
DOMAIN="panel.example.com"
FOREIGN="site.example.com"
SUBPATH_SNIPPET="adminpanelaz-panel_example_com-panel.conf"

mkdir -p "$TMP/bin"
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  -t)
    if [[ -f "${NGINX_FAIL_FLAG:?}" ]]; then
      echo "nginx: configuration file test failed" >&2
      exit 1
    fi
    ;;
  -v) echo "nginx version: nginx/1.24.0" >&2 ;;
esac
exit 0
EOF
cat >"$TMP/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "$*" >>"${SYSTEMCTL_LOG:?}"
exit 0
EOF
chmod +x "$TMP/bin/nginx" "$TMP/bin/systemctl"
export PATH="$TMP/bin:$PATH"

eval "$(sed -n '/^nginx_subpath_integrate_enabled() {/,/^}/p;/^nginx_finalize_nginx_site() {/,/^}/p' \
  "$ROOT_DIR/scripts/nginx-setup.sh")"
eval "$(sed -n '/^repair_nginx_for_panel() {/,/^}/p' "$ROOT_DIR/scripts/nginx-repair.sh")"
for f in nginx_finalize_nginx_site repair_nginx_for_panel; do
  declare -F "$f" >/dev/null || bad "$f не найдена"
done
# Предохранитель: функции с путём /etc/nginx в теле писали бы в настоящий nginx хоста.
if declare -f nginx_finalize_nginx_site repair_nginx_for_panel nginx_cleanup_subpath_snippets_for_domain \
  nginx_install_subpath_snippet _nginx_integrate_subpath_into_vhost_file \
  nginx_integrate_subpath_snippet_status_openvpn nginx_list_vhosts_for_domain \
  nginx_list_status_openvpn_vhosts_for_domain nginx_remove_our_dedicated_sites_for_domain \
  nginx_remove_all_vhosts_for_domain | grep -n '/etc/nginx' >&2; then
  echo "  FAIL функции subpath/repair используют /etc/nginx напрямую — тест не запускается" >&2
  exit 1
fi
print_access_url() { :; }
nginx_ensure_nginx() { :; }
nginx_resolve_panel_ssl_cert_paths() { NGINX_SSL_CERT=/cert.pem; NGINX_SSL_KEY=/key.pem; }
BACKEND_PORT=8000
HTTPS_PUBLIC_PORT=443
HTTP_ACME_PORT=80
PUBLISH_MODE=nginx_le

reset_tree() {
  rm -rf "$TMP/nginx" "$NGINX_FAIL_FLAG" "$SYSTEMCTL_LOG"
  mkdir -p "$NGINX_SNIPPETS_DIR" "$NGINX_BACKUPS_DIR" "$NGINX_CONF_D_DIR" \
    "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR"
  : >"$SYSTEMCTL_LOG"
}

# Рабочее состояние сервера: snippets Cloudflare уже подключены сайтами и отличаются от шаблона.
seed_cloudflare() {
  printf '# old realip\nset_real_ip_from 192.0.2.1;\nreal_ip_header CF-Connecting-IP;\n' \
    >"$NGINX_SNIPPETS_DIR/cloudflare-realip.conf"
  printf '# old allow\nallow 192.0.2.0/24;\n' >"$NGINX_SNIPPETS_DIR/cloudflare-origin-allow.conf"
  printf '# old lock\nif ($adminpanelaz_cf_origin = 0) { return 444; }\n' \
    >"$NGINX_SNIPPETS_DIR/cloudflare-origin-lock.conf"
  printf '# old geo\ngeo $realip_remote_addr $adminpanelaz_cf_origin {\n    default 0;\n}\n' \
    >"$NGINX_CONF_D_DIR/adminpanelaz-cloudflare-origin.conf"
  chmod 0600 "$NGINX_SNIPPETS_DIR/cloudflare-realip.conf"
}

# Чужой vhost домена: файл в sites-available, относительный симлинк в sites-enabled.
seed_foreign_vhost() {
  local body="${1:-}"
  local f="$NGINX_SITES_AVAILABLE_DIR/$FOREIGN"
  printf '# чужой сайт\nserver {\n    listen 443 ssl;\n    server_name %s;\n%s    root /srv/site;\n}\n' \
    "$DOMAIN" "$body" >"$f"
  chmod 0640 "$f"
  [[ "$(id -u)" -ne 0 ]] || chown 65534:65534 "$f"
  ln -s "../sites-available/$FOREIGN" "$NGINX_SITES_ENABLED_DIR/$FOREIGN"
}

seed_existing_subpath() {
  seed_foreign_vhost $'    # панель\n    include snippets/'"$SUBPATH_SNIPPET"$';\n'
  printf '# old subpath snippet\nlocation /panel/ { return 404; }\n' >"$NGINX_SNIPPETS_DIR/$SUBPATH_SNIPPET"
}

tree_state() {
  (
    cd "$TMP/nginx"
    find . -path ./backups -prune -o -printf '%p %y %m %u %l\n' | sort
    find . -path ./backups -prune -o -type f -print | sort | while IFS= read -r f; do sha256sum "$f"; done
  )
}

assert_tree_unchanged() {
  local now
  now="$(tree_state)"
  if [[ "$now" == "$BEFORE" ]]; then
    ok "$1"
  else
    bad "$1: $(diff <(printf '%s\n' "$BEFORE") <(printf '%s\n' "$now") | tr '\n' ' ')"
  fi
}

assert_no_leftovers() {
  local left
  left="$(find "$TMP/nginx" -name '.apaz-install*' -o -name '*.apaz-*' -o -name '*.tmp.*')"
  if [[ -z "$left" ]]; then
    ok "$1"
  else
    bad "$1: $left"
  fi
}

assert_failed_without_reload() {
  [[ "$rc" -ne 0 ]] && ok "установка упала" || bad "установка должна упасть"
  if grep -Eq '(^| )(reload|restart|start)( |$)' "$SYSTEMCTL_LOG"; then
    bad "nginx перезагружался после отката: $(tr '\n' ';' <"$SYSTEMCTL_LOG")"
  else
    ok "nginx не перезагружался"
  fi
}

assert_template() {
  local name="$1"
  if cmp -s "$NGINX_TEMPLATE_DIR/$name" "$NGINX_SNIPPETS_DIR/$name"; then
    ok "$name из шаблона"
  else
    bad "$name не из шаблона"
  fi
}

run_quiet() {
  set +e
  ( "$@" ) >"$TMP/out" 2>&1
  rc=$?
  set -e
}

nginx_fails() { : >"$NGINX_FAIL_FLAG"; }

subpath_install() {
  ACCESS_PATH=/panel NGINX_SUBPATH_INTEGRATE=true nginx_finalize_nginx_site "$DOMAIN" 8000
}

# Как nginx-setup.sh и install.sh: сначала subpath (при ACCESS_PATH пустом — только чистка),
# потом рендер в подоболочке и выделенный vhost.
root_install() {
  local conf
  ACCESS_PATH="" nginx_finalize_nginx_site "$DOMAIN" 8000 && return 0
  conf="$(ACCESS_PATH="" nginx_render_template "$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template" \
    "$DOMAIN" 8000 /cert.pem /key.pem 443 80)"
  nginx_install_site "$conf" "$DOMAIN"
}

echo "[test] subpath впервые: nginx -t не прошёл — чужой vhost, snippets и geo как до запуска"
reset_tree
seed_cloudflare
seed_foreign_vhost
BEFORE="$(tree_state)"
nginx_fails
run_quiet subpath_install
assert_failed_without_reload
assert_tree_unchanged "дерево nginx как до запуска (vhost байт-в-байт, симлинк, права)"
assert_no_leftovers "временных копий не осталось"
grep -qF 'откат' "$TMP/out" && ok "сообщение об откате" || bad "нет сообщения об откате: $(tail -3 "$TMP/out")"

echo "[test] subpath повторно (include и snippet уже есть): откат к прежним include и snippet"
reset_tree
seed_cloudflare
seed_existing_subpath
BEFORE="$(tree_state)"
nginx_fails
run_quiet subpath_install
assert_failed_without_reload
assert_tree_unchanged "дерево nginx как до запуска"
assert_no_leftovers "временных копий не осталось"

echo "[test] subpath в StatusOpenVPN (копия vhost в sites-enabled): откат без копий в sites-enabled"
reset_tree
seed_cloudflare
printf '# Created by StatusOpenVPN\nserver {\n    listen 443 ssl;\n    server_name %s;\n    location /status/ {\n        proxy_set_header X-Script-Name /status;\n    }\n}\n' \
  "$DOMAIN" >"$NGINX_SITES_ENABLED_DIR/status"
BEFORE="$(tree_state)"
nginx_fails
run_quiet subpath_install
assert_failed_without_reload
assert_tree_unchanged "дерево nginx как до запуска"
assert_no_leftovers "временных копий не осталось"

echo "[test] subpath: успешный nginx -t — изменения на месте, симлинк цел, копий нет"
reset_tree
seed_cloudflare
seed_existing_subpath
run_quiet subpath_install
[[ "$rc" -eq 0 ]] && ok "subpath прошёл" || bad "subpath упал: $(tail -3 "$TMP/out")"
if grep -qF "include snippets/${SUBPATH_SNIPPET};" "$NGINX_SITES_AVAILABLE_DIR/$FOREIGN"; then
  ok "include в чужом vhost"
else
  bad "нет include в чужом vhost"
fi
if [[ -L "$NGINX_SITES_ENABLED_DIR/$FOREIGN" \
  && "$(readlink "$NGINX_SITES_ENABLED_DIR/$FOREIGN")" == "../sites-available/$FOREIGN" ]]; then
  ok "симлинк sites-enabled не сломан"
else
  bad "симлинк sites-enabled сломан: $(ls -l "$NGINX_SITES_ENABLED_DIR/$FOREIGN")"
fi
[[ "$(stat -c %a "$NGINX_SITES_AVAILABLE_DIR/$FOREIGN")" == 640 ]] && ok "права vhost сохранены" || bad "права vhost изменились"
grep -qF 'old subpath snippet' "$NGINX_SNIPPETS_DIR/$SUBPATH_SNIPPET" && bad "snippet панели не обновлён" || ok "snippet панели обновлён"
assert_template cloudflare-realip.conf
assert_template cloudflare-origin-allow.conf
assert_no_leftovers "временных копий не осталось"
grep -q 'reload nginx' "$SYSTEMCTL_LOG" && ok "nginx перезагружен" || bad "nginx не перезагружен"

echo "[test] выделенный vhost панели: snippets Cloudflare в использовании — возвращён прежний вид"
reset_tree
seed_cloudflare
BEFORE="$(tree_state)"
nginx_fails
run_quiet nginx_install_dedicated_panel_vhost "$DOMAIN" 8000 /cert.pem /key.pem
assert_failed_without_reload
assert_tree_unchanged "snippets и geo как до установки"
assert_no_leftovers "временных копий не осталось"

echo "[test] snippets Cloudflare созданы этим запуском — после неудачи их нет"
reset_tree
BEFORE="$(tree_state)"
nginx_fails
run_quiet nginx_install_dedicated_panel_vhost "$DOMAIN" 8000 /cert.pem /key.pem
assert_failed_without_reload
assert_tree_unchanged "созданные snippets удалены"
assert_no_leftovers "временных копий не осталось"

echo "[test] портал: snippets пишутся в подоболочке рендера и тоже откатываются"
reset_tree
seed_cloudflare
BEFORE="$(tree_state)"
nginx_fails
run_quiet nginx_install_portal_vhost "portal.example.com" 8000 /cert.pem /key.pem
assert_failed_without_reload
assert_tree_unchanged "snippets и geo как до установки портала"
assert_no_leftovers "временных копий не осталось"

echo "[test] установщик / nginx-setup на корне: чистка subpath и snippets откатываются"
reset_tree
seed_cloudflare
seed_existing_subpath
BEFORE="$(tree_state)"
nginx_fails
run_quiet root_install
assert_failed_without_reload
assert_tree_unchanged "дерево nginx как до запуска"
assert_no_leftovers "временных копий не осталось"

echo "[test] nginx-repair: удалённые vhost домена, subpath и snippets возвращаются"
reset_tree
seed_cloudflare
seed_existing_subpath
BEFORE="$(tree_state)"
nginx_fails
ACCESS_PATH="" run_quiet repair_nginx_for_panel "$DOMAIN"
assert_failed_without_reload
assert_tree_unchanged "дерево nginx как до запуска"
assert_no_leftovers "временных копий не осталось"

echo "[test] успешная установка: snippets из шаблона, история в backups, копий нет"
reset_tree
seed_cloudflare
run_quiet nginx_install_dedicated_panel_vhost "$DOMAIN" 8000 /cert.pem /key.pem
[[ "$rc" -eq 0 ]] && ok "установка прошла" || bad "установка упала: $(tail -3 "$TMP/out")"
assert_template cloudflare-realip.conf
assert_template cloudflare-origin-allow.conf
assert_template cloudflare-origin-lock.conf
grep -rqF '# old realip' "$NGINX_BACKUPS_DIR" && ok "прежний realip в backups" || bad "прежнего realip нет в backups"
assert_no_leftovers "временных копий не осталось"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
