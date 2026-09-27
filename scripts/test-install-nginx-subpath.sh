#!/usr/bin/env bash
# install.sh и nginx-repair.sh подключают из библиотек nginx только nginx-common.sh: каждая функция
# nginx_*, которую они вызывают, должна быть определена там или в самом скрипте. Неопределённая функция
# в условии if не роняет скрипт (код 127 — просто «ложь»), а молча уводит в другую ветку.
# Установщик с подпутём на домене с чужим сайтом встраивает snippet в чужой vhost, а не ставит
# выделенный vhost панели на тот же домен; при неудачном nginx -t изменения откатываются.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# Не рабочий backend/.env: библиотека пишет в ENV_FILE.
ENV_FILE="$TMP/.env"
: >"$ENV_FILE"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

export NGINX_SNIPPETS_DIR="$TMP/nginx/snippets"
export NGINX_BACKUPS_DIR="$TMP/nginx/backups"
export NGINX_CONF_D_DIR="$TMP/nginx/conf.d"
export NGINX_SITES_AVAILABLE_DIR="$TMP/nginx/sites-available"
export NGINX_SITES_ENABLED_DIR="$TMP/nginx/sites-enabled"
export NGINX_ACME_WEBROOT="$TMP/www"
export NGINX_DEFAULT_DENY_CERT="$TMP/ssl/default-deny.crt"
export NGINX_DEFAULT_DENY_KEY="$TMP/ssl/default-deny.key"
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

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

# Предохранитель: каталоги nginx должны браться из переменных, иначе тест писал бы в nginx хоста.
for f in nginx_sites_available_dir nginx_sites_enabled_dir nginx_conf_d_dir nginx_backups_dir \
  nginx_snippets_dir nginx_acme_webroot nginx_default_deny_cert nginx_default_deny_key; do
  if [[ "$("$f")" != "$TMP"/* ]]; then
    echo "  FAIL $f не во временном каталоге: $("$f") — тест не запускается" >&2
    exit 1
  fi
done

# Имена режимов публикации (метки case и значения PUBLISH_MODE), а не функции.
PUBLISH_MODE_NAMES=" nginx_le nginx_selfsigned nginx_custom "

# Функции nginx_*, упомянутые в скрипте, но не определённые ни в nginx-common.sh, ни в нём самом.
undefined_nginx_functions() {
  local script="$1" f missing=""
  for f in $(grep -oE '\bnginx_[a-zA-Z0-9_]+\b' "$script" | sort -u); do
    [[ "$PUBLISH_MODE_NAMES" == *" $f "* ]] && continue
    declare -F "$f" >/dev/null && continue
    grep -qE "^[[:space:]]*${f}\(\)" "$script" && continue
    missing+=" $f"
  done
  printf '%s' "${missing# }"
}

echo "[test] функции nginx_* из install.sh, nginx-setup.sh и nginx-repair.sh определены после source nginx-common.sh"
for script in install.sh scripts/nginx-setup.sh scripts/nginx-repair.sh; do
  missing="$(undefined_nginx_functions "$ROOT_DIR/$script")"
  if [[ -z "$missing" ]]; then
    ok "$script"
  else
    bad "$script: не определены: $missing"
  fi
done

eval "$(sed -n '/^setup_nginx_if_selected() {/,/^}/p' "$ROOT_DIR/install.sh")"
declare -F setup_nginx_if_selected >/dev/null || { echo "  FAIL setup_nginx_if_selected не найдена в install.sh" >&2; exit 1; }
if declare -f setup_nginx_if_selected | grep -n '/etc/nginx' >&2; then
  echo "  FAIL setup_nginx_if_selected использует /etc/nginx напрямую — тест не запускается" >&2
  exit 1
fi
wiz_config_active() { return 0; }
install_controller_selected() { return 0; }
install_set_step() { :; }
log() { echo "[install] $*" >&2; }
warn() { echo "[install] ВНИМАНИЕ: $*" >&2; }
die() { echo "[install] ОШИБКА: $*" >&2; exit 1; }

mkdir -p "$TMP/ssl"
: >"$TMP/ssl/panel.crt"
: >"$TMP/ssl/panel.key"
export WIZ_NGINX_MODE=nginx_custom
export WIZ_NGINX_DOMAIN="$DOMAIN"
export WIZ_ACCESS_PATH=/panel
export WIZ_NGINX_SUBPATH_INTEGRATE=true
export WIZ_APP_ENV=production
export WIZ_BACKEND_PORT=8000
export WIZ_SSL_CERT="$TMP/ssl/panel.crt"
export WIZ_SSL_KEY="$TMP/ssl/panel.key"

reset_tree() {
  rm -rf "$TMP/nginx" "$NGINX_FAIL_FLAG"
  mkdir -p "$NGINX_SNIPPETS_DIR" "$NGINX_BACKUPS_DIR" "$NGINX_CONF_D_DIR" \
    "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR"
  : >"$SYSTEMCTL_LOG"
  : >"$ENV_FILE"
  local f="$NGINX_SITES_AVAILABLE_DIR/$FOREIGN"
  printf '# чужой сайт\nserver {\n    listen 443 ssl;\n    server_name %s;\n    root /srv/site;\n}\n' \
    "$DOMAIN" >"$f"
  ln -s "../sites-available/$FOREIGN" "$NGINX_SITES_ENABLED_DIR/$FOREIGN"
}

tree_state() {
  (
    cd "$TMP/nginx"
    find . -path ./backups -prune -o -printf '%p %y %m %u %l\n' | sort
    find . -path ./backups -prune -o -type f -print | sort | while IFS= read -r f; do sha256sum "$f"; done
  )
}

run_install() {
  set +e
  ( setup_nginx_if_selected ) >"$TMP/out" 2>&1
  rc=$?
  set -e
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

echo "[test] установщик: подпуть на домене с чужим сайтом — snippet в чужом vhost, без выделенного vhost"
reset_tree
run_install
[[ "$rc" -eq 0 ]] && ok "установка прошла" || bad "установка упала (rc=$rc): $(tail -3 "$TMP/out")"
if grep -qF 'command not found' "$TMP/out"; then
  bad "вызов неопределённой команды: $(grep -F 'command not found' "$TMP/out" | head -3 | tr '\n' ' ')"
else
  ok "нет вызовов неопределённых команд"
fi
if grep -qF "include snippets/${SUBPATH_SNIPPET};" "$NGINX_SITES_AVAILABLE_DIR/$FOREIGN"; then
  ok "include snippet в чужом vhost"
else
  bad "нет include snippet в чужом vhost"
fi
[[ -f "$NGINX_SNIPPETS_DIR/$SUBPATH_SNIPPET" ]] && ok "snippet панели создан" || bad "нет snippet панели"
if [[ -e "$NGINX_SITES_AVAILABLE_DIR/panel_example_com" || -e "$NGINX_SITES_ENABLED_DIR/panel_example_com" ]]; then
  bad "поставлен выделенный vhost панели на домен чужого сайта"
else
  ok "выделенного vhost панели нет"
fi
if [[ -L "$NGINX_SITES_ENABLED_DIR/$FOREIGN" ]]; then
  ok "симлинк чужого сайта в sites-enabled цел"
else
  bad "симлинк чужого сайта сломан"
fi
grep -qx 'reload nginx' "$SYSTEMCTL_LOG" && ok "nginx перезагружен (reload)" || bad "nginx не перезагружен: $(tr '\n' ';' <"$SYSTEMCTL_LOG")"
grep -qx 'restart nginx' "$SYSTEMCTL_LOG" && bad "nginx перезапускался (restart), как для выделенного vhost" || ok "nginx не перезапускался"
grep -qx 'ACCESS_PATH=/panel' "$ENV_FILE" && ok "ACCESS_PATH=/panel в .env" || bad "нет ACCESS_PATH=/panel в .env"
grep -qx 'BEHIND_NGINX=true' "$ENV_FILE" && ok "BEHIND_NGINX=true в .env" || bad "нет BEHIND_NGINX=true в .env"
assert_no_leftovers "копий отката не осталось"

echo "[test] установщик: подпуть, nginx -t не прошёл — дерево nginx как до запуска, без reload"
reset_tree
BEFORE="$(tree_state)"
: >"$NGINX_FAIL_FLAG"
run_install
[[ "$rc" -ne 0 ]] && ok "установка упала" || bad "установка должна упасть"
now="$(tree_state)"
if [[ "$now" == "$BEFORE" ]]; then
  ok "дерево nginx как до запуска"
else
  bad "дерево nginx изменилось: $(diff <(printf '%s\n' "$BEFORE") <(printf '%s\n' "$now") | tr '\n' ' ')"
fi
if grep -Eq '(^| )(reload|restart|start)( |$)' "$SYSTEMCTL_LOG"; then
  bad "nginx перезагружался после отката: $(tr '\n' ';' <"$SYSTEMCTL_LOG")"
else
  ok "nginx не перезагружался"
fi
grep -qF 'откатаны' "$TMP/out" && ok "сообщение об откате" || bad "нет сообщения об откате: $(tail -3 "$TMP/out")"
grep -qF 'встраивания snippet' "$TMP/out" && ok "откат из ветки subpath" || bad "откат не из ветки subpath: $(tail -3 "$TMP/out")"
assert_no_leftovers "копий отката не осталось"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
