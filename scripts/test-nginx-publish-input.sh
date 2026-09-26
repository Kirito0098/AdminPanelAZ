#!/usr/bin/env bash
# Домен, пути сертификатов и любые значения .env не должны добавлять ключи в .env или директивы в vhost,
# а ошибка рендера шаблона не должна ставить пустой vhost.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
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
mkdir -p "$NGINX_SNIPPETS_DIR" "$NGINX_BACKUPS_DIR" "$NGINX_CONF_D_DIR" \
  "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR" "$TMP/bin"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/bin/nginx"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/bin/systemctl"
chmod +x "$TMP/bin/nginx" "$TMP/bin/systemctl"
export PATH="$TMP/bin:$PATH"

run_quiet() {
  set +e
  ( "$@" ) >"$TMP/out" 2>&1
  rc=$?
  set -e
}

echo "[test] nginx_env_set: перевод строки в значении не добавляет ключ"
printf 'DOMAIN=old.example.com\n' >"$ENV_FILE"
run_quiet nginx_env_set DOMAIN $'x.example.com\nFRONTEND_DIST_PATH=/'
[[ "$rc" -ne 0 ]] && ok "запись отклонена" || bad "запись должна быть отклонена"
grep -q '^FRONTEND_DIST_PATH=' "$ENV_FILE" && bad "в .env появился новый ключ" || ok "нового ключа нет"
grep -qx 'DOMAIN=old.example.com' "$ENV_FILE" && ok "прежнее значение сохранено" || bad "значение изменилось: $(cat "$ENV_FILE")"
run_quiet nginx_env_set NEW_KEY $'a\rb'
[[ "$rc" -ne 0 ]] && ok "\\r отклонён для нового ключа" || bad "\\r должен быть отклонён"
grep -q '^NEW_KEY=' "$ENV_FILE" && bad "новый ключ записан" || ok "новый ключ не записан"

echo "[test] nginx_env_set: обратный слеш записывается буквально"
printf 'CORS_ORIGINS=old\n' >"$ENV_FILE"
run_quiet nginx_env_set CORS_ORIGINS 'a\nb\\c&d|e'
[[ "$rc" -eq 0 ]] && ok "запись прошла" || bad "запись упала: $(cat "$TMP/out")"
[[ "$(grep -c '' "$ENV_FILE")" -eq 1 ]] && ok "в .env одна строка" || bad "строк больше одной: $(cat "$ENV_FILE")"
grep -qxF 'CORS_ORIGINS=a\nb\\c&d|e' "$ENV_FILE" && ok "значение буквальное" || bad "значение искажено: $(cat "$ENV_FILE")"

TEMPLATE="$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template"
for domain in 'x.example.com; location /leak { alias /etc/; }' $'x.example.com\nserver_name y' 'x.example.com|y' 'x.example.com\y'; do
  echo "[test] рендер отклоняет домен: ${domain//$'\n'/\\n}"
  run_quiet nginx_render_template "$TEMPLATE" "$domain" 8000 /etc/ssl/a.pem /etc/ssl/a.key
  [[ "$rc" -ne 0 ]] && ok "панель: рендер упал" || bad "панель: рендер должен упасть: $(cat "$TMP/out")"
  run_quiet nginx_render_portal_template "$domain" 8000 /etc/ssl/a.pem /etc/ssl/a.key
  [[ "$rc" -ne 0 ]] && ok "портал: рендер упал" || bad "портал: рендер должен упасть"
done

echo "[test] рендер отклоняет путь сертификата с директивой"
run_quiet nginx_render_template "$TEMPLATE" panel.example.com 8000 '/etc/ssl/a.pem; include /etc/shadow' /etc/ssl/a.key
[[ "$rc" -ne 0 ]] && ok "рендер упал" || bad "рендер должен упасть"

echo "[test] рендер нормального домена и IPv4"
run_quiet nginx_render_template "$TEMPLATE" panel.example.com 8000 /etc/letsencrypt/live/panel.example.com/fullchain.pem /etc/ssl/a.key
[[ "$rc" -eq 0 ]] && grep -q 'server_name panel.example.com' "$TMP/out" && ok "домен" || bad "домен не отрендерен: $(cat "$TMP/out")"
run_quiet nginx_render_template "$TEMPLATE" 203.0.113.10 8000 /etc/ssl/a.pem /etc/ssl/a.key
[[ "$rc" -eq 0 ]] && grep -q 'server_name 203.0.113.10' "$TMP/out" && ok "IPv4" || bad "IPv4 не отрендерен: $(cat "$TMP/out")"

echo "[test] сбой sed при рендере не ставит пустой vhost"
sed() { if [[ " $* " == *"__DOMAIN__"* ]]; then return 4; fi; command sed "$@"; }
run_quiet nginx_install_dedicated_panel_vhost panel.example.com 8000 /etc/ssl/a.pem /etc/ssl/a.key
unset -f sed
[[ "$rc" -ne 0 ]] && ok "установка упала" || bad "установка должна упасть"
if [[ ! -e "$NGINX_SITES_AVAILABLE_DIR/$(nginx_conf_basename panel.example.com)" ]]; then
  ok "пустой vhost не создан"
else
  bad "создан vhost: '$(cat "$NGINX_SITES_AVAILABLE_DIR/$(nginx_conf_basename panel.example.com)")'"
fi

echo "[test] nginx_install_site отказывается ставить пустую конфигурацию"
run_quiet nginx_install_site "" panel.example.com
[[ "$rc" -ne 0 ]] && ok "отказ" || bad "пустая конфигурация установлена"
[[ ! -e "$NGINX_SITES_AVAILABLE_DIR/$(nginx_conf_basename panel.example.com)" ]] && ok "файла нет" || bad "файл создан"

printf '#!/usr/bin/env bash\necho 0\n' >"$TMP/bin/id"
chmod +x "$TMP/bin/id"
run_setup() {
  set +e
  env "$@" ENV_FILE="$ENV_FILE" bash "$ROOT_DIR/scripts/nginx-setup.sh" --non-interactive "$flag" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

for flag in --uvicorn-custom --nginx-custom --uvicorn-selfsigned --nginx-selfsigned; do
  for domain in $'x.example.com\nFRONTEND_DIST_PATH=/' 'x.example.com;proxy_pass'; do
    echo "[test] nginx-setup.sh $flag: домен ${domain//$'\n'/\\n} останавливает публикацию до изменений"
    printf 'DOMAIN=old.example.com\n' >"$ENV_FILE"
    run_setup DOMAIN="$domain" SSL_CERT=/etc/hostname SSL_KEY=/etc/hostname
    [[ "$rc" -ne 0 ]] && grep -q 'Неверный формат домена' "$TMP/out" && ok "отказ" || bad "нет отказа: $(cat "$TMP/out")"
    [[ "$(cat "$ENV_FILE")" == "DOMAIN=old.example.com" ]] && ok ".env не изменён" || bad ".env изменён: $(cat "$ENV_FILE")"
  done
done

for flag in --uvicorn-custom --nginx-custom; do
  echo "[test] nginx-setup.sh $flag: путь сертификата с директивой отклоняется"
  printf 'DOMAIN=old.example.com\n' >"$ENV_FILE"
  run_setup DOMAIN=panel.example.com SSL_CERT='/etc/hostname;include' SSL_KEY=/etc/hostname
  [[ "$rc" -ne 0 ]] && grep -q 'Недопустимый путь' "$TMP/out" && ok "отказ" || bad "нет отказа: $(cat "$TMP/out")"
  [[ "$(cat "$ENV_FILE")" == "DOMAIN=old.example.com" ]] && ok ".env не изменён" || bad ".env изменён: $(cat "$ENV_FILE")"
done

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
