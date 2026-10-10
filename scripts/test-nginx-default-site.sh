#!/usr/bin/env bash
# Установка сайта панели и временный ACME-vhost убирают sites-enabled/default, только если это стоковый
# симлинк пакета nginx на sites-available/default (Debian ставит абсолютный путь, вручную делают
# относительный). Изменённый default — чужой сайт, он остаётся. Неудачный nginx -t возвращает симлинк.
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
DEFAULT="$NGINX_SITES_ENABLED_DIR/default"

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

reset_tree() {
  rm -rf "$TMP/nginx" "$NGINX_FAIL_FLAG"
  mkdir -p "$NGINX_SNIPPETS_DIR" "$NGINX_BACKUPS_DIR" "$NGINX_CONF_D_DIR" \
    "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR"
  : >"$SYSTEMCTL_LOG"
  printf 'server {\n    listen 80 default_server;\n    root /var/www/html;\n}\n' >"$NGINX_SITES_AVAILABLE_DIR/default"
}

run_quiet() {
  set +e
  ( "$@" ) >"$TMP/out" 2>&1
  rc=$?
  set -e
}

install_panel() {
  nginx_install_dedicated_panel_vhost "$DOMAIN" 8000 /cert.pem /key.pem
}

for target in "$NGINX_SITES_AVAILABLE_DIR/default" ../sites-available/default; do
  echo "[test] стоковый default ($target) убирается при установке сайта панели"
  reset_tree
  ln -s "$target" "$DEFAULT"
  run_quiet install_panel
  [[ "$rc" -eq 0 ]] && ok "установка прошла" || bad "установка упала: $(tail -3 "$TMP/out")"
  [[ ! -e "$DEFAULT" && ! -L "$DEFAULT" ]] && ok "default убран" || bad "default остался"
  [[ -f "$NGINX_SITES_AVAILABLE_DIR/default" ]] && ok "sites-available/default не тронут" || bad "sites-available/default удалён"
done

echo "[test] изменённый default (файл, а не симлинк) — чужой сайт, остаётся"
reset_tree
printf 'server {\n    listen 80 default_server;\n    root /srv/own;\n}\n' >"$DEFAULT"
cp "$DEFAULT" "$TMP/default.before"
run_quiet install_panel
[[ "$rc" -eq 0 ]] && ok "установка прошла" || bad "установка упала: $(tail -3 "$TMP/out")"
if [[ -f "$DEFAULT" && ! -L "$DEFAULT" ]] && cmp -s "$DEFAULT" "$TMP/default.before"; then
  ok "default на месте и не изменён"
else
  bad "default удалён или изменён"
fi

echo "[test] default — симлинк на другой сайт, остаётся"
reset_tree
printf 'server { listen 80; server_name own.example; }\n' >"$NGINX_SITES_AVAILABLE_DIR/own"
ln -s ../sites-available/own "$DEFAULT"
run_quiet install_panel
[[ "$rc" -eq 0 ]] && ok "установка прошла" || bad "установка упала: $(tail -3 "$TMP/out")"
if [[ -L "$DEFAULT" && "$(readlink "$DEFAULT")" == ../sites-available/own ]]; then
  ok "симлинк default не тронут"
else
  bad "симлинк default удалён или изменён"
fi

echo "[test] nginx -t не прошёл — стоковый default возвращается"
reset_tree
ln -s ../sites-available/default "$DEFAULT"
: >"$NGINX_FAIL_FLAG"
run_quiet install_panel
[[ "$rc" -ne 0 ]] && ok "установка упала" || bad "установка должна упасть"
if [[ -L "$DEFAULT" && "$(readlink "$DEFAULT")" == ../sites-available/default ]]; then
  ok "default возвращён"
else
  bad "default не возвращён: $(ls -la "$NGINX_SITES_ENABLED_DIR" | tr '\n' ';')"
fi
left="$(find "$TMP/nginx" -name '.apaz-install*' -o -name '*.apaz-*')"
[[ -z "$left" ]] && ok "копий отката не осталось" || bad "остались: $left"

echo "[test] временный ACME-vhost: изменённый default остаётся, стоковый убирается и возвращается"
reset_tree
printf 'server {\n    listen 80 default_server;\n    root /srv/own;\n}\n' >"$DEFAULT"
run_quiet nginx_install_temp_acme_http_vhost portal.example.com 80
[[ "$rc" -eq 0 ]] && ok "ACME-vhost поставлен" || bad "ACME-vhost: $(tail -3 "$TMP/out")"
[[ -f "$DEFAULT" ]] && ok "изменённый default на месте" || bad "изменённый default удалён"
reset_tree
ln -s ../sites-available/default "$DEFAULT"
run_quiet nginx_install_temp_acme_http_vhost portal.example.com 80
[[ ! -e "$DEFAULT" && ! -L "$DEFAULT" ]] && ok "стоковый default убран на время ACME" || bad "стоковый default остался"
run_quiet nginx_remove_temp_acme_http_vhost portal.example.com
if [[ -L "$DEFAULT" && "$(readlink "$DEFAULT")" == ../sites-available/default ]]; then
  ok "стоковый default возвращён"
else
  bad "default не возвращён"
fi

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
