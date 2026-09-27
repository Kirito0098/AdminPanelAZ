#!/usr/bin/env bash
# scripts/nginx-default-deny.sh: --check сообщает, закрыт ли доступ к панели по IP, --apply ставит только
# сервер по умолчанию и перечитывает nginx (reload, не restart). nginx, systemctl и id подменены в PATH.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/nginx-default-deny.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export ENV_FILE="$TMP/.env"
: >"$ENV_FILE"
export NGINX_SITES_AVAILABLE_DIR="$TMP/sites-available"
export NGINX_SITES_ENABLED_DIR="$TMP/sites-enabled"
export NGINX_CONF_D_DIR="$TMP/conf.d"
export NGINX_DEFAULT_DENY_CERT="$TMP/ssl/deny.crt"
export NGINX_DEFAULT_DENY_KEY="$TMP/ssl/deny.key"
export NGINX_DEFAULT_DENY_LOCK="$TMP/default-deny.lock"
export FAKE_LOG="$TMP/calls.log"
export FAKE_UID=0
export FAKE_NGINX_VERSION="1.24.0"
export FAKE_T_FAIL_WITH_DENY=0
export FAKE_RELOAD_FAIL=0
AVAIL="$NGINX_SITES_AVAILABLE_DIR"
ENABLED="$NGINX_SITES_ENABLED_DIR"
DENY="$AVAIL/00-adminpanelaz-default-deny"
DENY_LINK="$ENABLED/00-adminpanelaz-default-deny"

mkdir -p "$TMP/bin" "$AVAIL" "$ENABLED" "$NGINX_CONF_D_DIR"
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  -v) echo "nginx version: nginx/${FAKE_NGINX_VERSION}" >&2 ;;
  -t)
    echo "nginx -t" >>"$FAKE_LOG"
    if [[ "$FAKE_T_FAIL_WITH_DENY" == 1 && -e "$NGINX_SITES_ENABLED_DIR/00-adminpanelaz-default-deny" ]]; then
      echo "nginx: [emerg] duplicate default server" >&2
      exit 1
    fi
    ;;
esac
exit 0
EOF
cat >"$TMP/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >>"$FAKE_LOG"
[[ "${1:-}" == reload && "$FAKE_RELOAD_FAIL" == 1 ]] && exit 1
exit 0
EOF
cat >"$TMP/bin/id" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == -u ]] && { echo "$FAKE_UID"; exit 0; }
exec /usr/bin/id "$@"
EOF
chmod +x "$TMP/bin/nginx" "$TMP/bin/systemctl" "$TMP/bin/id"
export PATH="$TMP/bin:$PATH"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }
check() { if eval "$1"; then ok "$2"; else bad "$2"; fi; }

PANEL_CONF='# AdminPanelAZ — Nginx reverse proxy (шаблон)
server {
    listen 8080;
    server_name panel.example.com;
}
server {
    listen 8443 ssl http2;
    server_name panel.example.com;
}'

reset() {
  rm -rf "${AVAIL:?}"/* "${ENABLED:?}"/* "${NGINX_CONF_D_DIR:?}"/* "$TMP/ssl"
  : >"$FAKE_LOG"
  FAKE_UID=0
  FAKE_NGINX_VERSION="1.24.0"
  FAKE_T_FAIL_WITH_DENY=0
  FAKE_RELOAD_FAIL=0
}

# site <имя> <содержимое>: включённый сайт в sites-enabled
site() {
  printf '%s\n' "$2" >"$AVAIL/$1"
  ln -sf "$AVAIL/$1" "$ENABLED/$1"
}

# run <аргументы>: stdout → $out, код выхода → $rc
run() {
  rc=0
  out="$(bash "$SCRIPT" "$@" 2>"$TMP/stderr")" || rc=$?
}

has() { [[ "$out" == *"$1"* ]]; }
lines() { printf '%s\n' "$out" | grep -c . || true; }

echo "[test] --help и неизвестный аргумент"
run --help
check '[[ "$rc" == 0 ]] && has "--check" && has "--apply"' "--help: справка, код 0"
run --bogus
check '[[ "$rc" != 0 ]]' "неизвестный аргумент: ненулевой код"

echo "[test] не root — ошибка без изменений"
reset
site panel_example_com "$PANEL_CONF"
FAKE_UID=1000
run --apply
check '[[ "$rc" != 0 ]]' "ненулевой код"
check 'grep -q "root" "$TMP/stderr"' "сообщение про root"
check '[[ ! -e "$DENY" ]]' "файл не создан"

echo "[test] --check: сервер по умолчанию нужен (needed), файлы не меняются"
reset
site panel_example_com "$PANEL_CONF"
run --check
check '[[ "$rc" == 0 ]]' "код 0"
check '[[ "$(lines)" == 1 ]]' "одна строка вывода"
check 'has "\"status\":\"needed\""' "status=needed"
check 'has "\"installed\":false"' "installed=false"
check 'has "{\"port\":8080,\"kind\":\"http\",\"action\":\"install\"}"' "8080: install http"
check 'has "{\"port\":8443,\"kind\":\"https\",\"action\":\"install\"}"' "8443: install https"
check '[[ ! -e "$DENY" && ! -L "$DENY_LINK" ]]' "--check ничего не пишет"
check '! grep -q "systemctl" "$FAKE_LOG"' "--check не трогает systemctl"

echo "[test] --apply: ставит default-deny и делает reload (не restart)"
run --apply
check '[[ "$rc" == 0 ]]' "код 0"
check '[[ "$(lines)" == 1 ]]' "одна строка вывода"
check 'has "\"status\":\"installed\"" && has "\"changed\":true"' "status=installed, changed=true"
check '[[ -L "$DENY_LINK" ]] && grep -q "listen 8080 default_server;" "$DENY" && grep -q "listen 8443 ssl default_server;" "$DENY"' "default-deny на обоих портах"
check '[[ "$(grep -c "systemctl reload nginx" "$FAKE_LOG")" == 1 ]]' "один systemctl reload nginx"
check '! grep -q "restart" "$FAKE_LOG"' "без restart"
check '[[ "$(cat "$AVAIL/panel_example_com")" == "$PANEL_CONF" ]]' "vhost панели не переписан"
check '[[ ! -s "$ENV_FILE" ]]' ".env не менялся"

echo "[test] --check после --apply: installed"
run --check
check '[[ "$rc" == 0 ]] && has "\"status\":\"installed\"" && has "\"installed\":true"' "status=installed"

echo "[test] повторный --apply без изменений не перезагружает nginx"
: >"$FAKE_LOG"
run --apply
check '[[ "$rc" == 0 ]] && has "\"status\":\"installed\"" && has "\"changed\":false"' "changed=false"
check '! grep -q "systemctl" "$FAKE_LOG"' "reload не вызывался"

echo "[test] outdated: портал добавил порт — --check outdated, --apply обновляет"
site portal_example_com '# AdminPanelAZ — Client portal reverse proxy (шаблон)
server {
    listen 9080;
    server_name portal.example.com;
}'
: >"$FAKE_LOG"
run --check
check '[[ "$rc" == 0 ]] && has "\"status\":\"outdated\""' "status=outdated"
check 'has "{\"port\":9080,\"kind\":\"http\",\"action\":\"install\"}"' "9080 в плане"
run --apply
check '[[ "$rc" == 0 ]] && has "\"status\":\"installed\"" && has "\"changed\":true"' "обновлён"
check 'grep -q "listen 9080 default_server;" "$DENY"' "9080 закрыт"
check '[[ "$(grep -c "systemctl reload nginx" "$FAKE_LOG")" == 1 ]]' "reload после обновления"

echo "[test] outdated: портов панели больше нет — --apply убирает default-deny"
rm -f "$ENABLED/panel_example_com" "$ENABLED/portal_example_com"
: >"$FAKE_LOG"
run --check
check 'has "\"status\":\"outdated\""' "status=outdated"
run --apply
check '[[ "$rc" == 0 ]] && has "\"status\":\"not_applicable\"" && has "\"changed\":true"' "status=not_applicable, changed=true"
check '[[ ! -e "$DENY" && ! -L "$DENY_LINK" ]]' "default-deny убран"
check 'grep -q "systemctl reload nginx" "$FAKE_LOG"' "reload после удаления"

echo "[test] own_default: свой default_server администратора закрывает порты панели"
reset
site aaa-stub 'server {
    listen 8080 default_server;
    listen 8443 ssl default_server;
    return 444;
}'
site panel_example_com "$PANEL_CONF"
run --check
check '[[ "$rc" == 0 ]] && has "\"status\":\"own_default\""' "status=own_default"
check 'has "{\"port\":8080,\"kind\":\"http\",\"action\":\"skip\",\"reason\":\"existing_default_server\"}"' "причина existing_default_server"

echo "[test] частично: на 8080 свой default_server, 8443 закрыть нужно"
reset
site aaa-stub 'server { listen 8080 default_server; return 444; }'
site panel_example_com "$PANEL_CONF"
run --check
check 'has "\"status\":\"needed\"" && has "\"reason\":\"existing_default_server\""' "status=needed с пропущенным портом"

echo "[test] not_applicable: чужой сайт объявлен первым на всех портах"
reset
site aaa 'server { listen 8080; listen 8443 ssl; server_name a.example; }'
site panel_example_com "$PANEL_CONF"
run --check
check '[[ "$rc" == 0 ]] && has "\"status\":\"not_applicable\""' "status=not_applicable"
check 'has "\"reason\":\"foreign_first\""' "причина foreign_first"
run --apply
check '[[ "$rc" == 0 && ! -e "$DENY" ]] && has "\"changed\":false"' "--apply ничего не ставит"
check '! grep -q "systemctl" "$FAKE_LOG"' "без reload"

echo "[test] not_applicable: vhost панели нет (прямая публикация uvicorn)"
reset
site other 'server { listen 80; server_name other.example; }'
run --check
check '[[ "$rc" == 0 ]] && has "\"status\":\"not_applicable\"" && has "\"ports\":[]"' "status=not_applicable, портов нет"

echo "[test] панель по IP: HTTPS-порт пропускается (ip_server_name), HTTP закрывается"
reset
site panel_203 "${PANEL_CONF//panel.example.com/203.0.113.10}"
run --check
check 'has "\"status\":\"needed\""' "status=needed"
check 'has "{\"port\":8443,\"kind\":\"https\",\"action\":\"skip\",\"reason\":\"ip_server_name\"}"' "8443: ip_server_name"

echo "[test] nginx 1.18: самоподписанный сертификат, повторная проверка — installed"
reset
FAKE_NGINX_VERSION="1.18.0"
site panel_example_com "$PANEL_CONF"
run --apply
check '[[ "$rc" == 0 ]] && has "\"status\":\"installed\""' "установлен"
check 'grep -q "ssl_certificate $NGINX_DEFAULT_DENY_CERT;" "$DENY"' "свой сертификат"
run --check
check 'has "\"status\":\"installed\""' "--check: installed"

echo "[test] nginx 1.18 без openssl: закрывается только HTTP, --apply успешен, --check сообщает про HTTPS"
reset
FAKE_NGINX_VERSION="1.18.0"
site panel_example_com "$PANEL_CONF"
printf '#!/usr/bin/env bash\nexit 1\n' >"$TMP/bin/openssl"
chmod +x "$TMP/bin/openssl"
run --check
check 'has "\"status\":\"needed\""' "--check до установки: needed"
check 'has "{\"port\":8080,\"kind\":\"http\",\"action\":\"install\"}"' "8080: install"
check 'has "{\"port\":8443,\"kind\":\"https\",\"action\":\"skip\",\"reason\":\"no_cert\"}"' "8443: skip no_cert"
run --apply
check '[[ "$rc" == 0 ]] && has "\"status\":\"installed\"" && has "\"changed\":true"' "--apply: installed, changed=true"
check '! has "\"error\""' "без error"
check 'grep -q "listen 8080 default_server;" "$DENY" && ! grep -q "ssl" "$DENY"' "в файле только HTTP"
check 'grep -q "сертификат" "$TMP/stderr"' "предупреждение про сертификат"
check '[[ "$(grep -c "systemctl reload nginx" "$FAKE_LOG")" == 1 ]]' "reload"
run --check
check 'has "\"status\":\"installed\"" && has "\"reason\":\"no_cert\""' "--check: installed, 8443 no_cert"
rm -f "$TMP/bin/openssl"
: >"$FAKE_LOG"
run --apply
check '[[ "$rc" == 0 ]] && has "\"status\":\"installed\"" && has "\"changed\":true" && ! has "no_cert"' "openssl починили — --apply добавляет HTTPS"
check 'grep -q "listen 8443 ssl default_server;" "$DENY"' "8443 закрыт"

echo "[test] --apply: занятая блокировка — ждёт, по тайм-ауту выходит без изменений"
reset
site panel_example_com "$PANEL_CONF"
hold_lock() {
  (
    exec 9>"$NGINX_DEFAULT_DENY_LOCK"
    flock 9
    exec sleep "$1"
  ) &
  holder=$!
  until ! flock -n "$NGINX_DEFAULT_DENY_LOCK" true; do sleep 0.05; done
}
hold_lock 30
NGINX_DEFAULT_DENY_LOCK_WAIT=1 run --apply
check '[[ "$rc" != 0 ]]' "ненулевой код"
check 'grep -q "не завершился за 1 с" "$TMP/stderr"' "сообщение про параллельный запуск"
check '[[ ! -e "$DENY" && ! -L "$DENY_LINK" ]]' "файлы не тронуты"
check '! grep -q "nginx -t\|systemctl" "$FAKE_LOG"' "nginx и systemctl не вызывались"
kill "$holder" 2>/dev/null || true
wait "$holder" 2>/dev/null || true
hold_lock 1
NGINX_DEFAULT_DENY_LOCK_WAIT=10 run --apply
check '[[ "$rc" == 0 ]] && has "\"status\":\"installed\""' "дождался освобождения и установил"
wait "$holder" 2>/dev/null || true
hold_lock 30
NGINX_DEFAULT_DENY_LOCK_WAIT=1 run --check
check '[[ "$rc" == 0 ]] && has "\"status\":\"installed\""' "--check не ждёт блокировку"
kill "$holder" 2>/dev/null || true
wait "$holder" 2>/dev/null || true

echo "[test] --apply: nginx -t не прошёл — откат, без reload, ненулевой код"
reset
site panel_example_com "$PANEL_CONF"
FAKE_T_FAIL_WITH_DENY=1
run --apply
check '[[ "$rc" != 0 ]]' "ненулевой код"
check '[[ "$(lines)" == 1 ]] && has "\"status\":\"needed\"" && has "\"error\":\"install_failed\""' "status=needed, error=install_failed"
check '[[ ! -e "$DENY" && ! -L "$DENY_LINK" ]]' "default-deny убран"
check '! grep -q "systemctl" "$FAKE_LOG"' "reload не вызывался"

echo "[test] --apply: новая версия не прошла nginx -t — прежний default-deny возвращается"
reset
site panel_example_com "$PANEL_CONF"
run --apply
old="$(cat "$DENY")"
site portal_example_com '# AdminPanelAZ — Client portal reverse proxy (шаблон)
server { listen 9080; server_name portal.example.com; }'
: >"$FAKE_LOG"
# nginx -t падает только на новой версии: прежняя без 9080
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  -v) echo "nginx version: nginx/${FAKE_NGINX_VERSION}" >&2 ;;
  -t)
    echo "nginx -t" >>"$FAKE_LOG"
    if grep -qs "listen 9080 default_server" "$NGINX_SITES_ENABLED_DIR/00-adminpanelaz-default-deny"; then
      exit 1
    fi
    ;;
esac
exit 0
EOF
run --apply
check '[[ "$rc" != 0 ]] && has "\"error\":\"install_failed\""' "ненулевой код, error=install_failed"
check '[[ -L "$DENY_LINK" && "$(cat "$DENY")" == "$old" ]]' "прежний default-deny восстановлен"
check '! grep -q "systemctl" "$FAKE_LOG"' "reload не вызывался"

echo "[test] --apply: reload не удался — ненулевой код"
reset
site panel_example_com "$PANEL_CONF"
FAKE_RELOAD_FAIL=1
run --apply
check '[[ "$rc" != 0 ]] && has "\"error\":\"reload_failed\""' "error=reload_failed"
check '[[ -L "$DENY_LINK" ]]' "конфиг остаётся (прошёл nginx -t)"

echo "[test] NGINX_DEFAULT_DENY=0: --check — disabled, файлы не меняются"
reset
site panel_example_com "$PANEL_CONF"
echo "NGINX_DEFAULT_DENY=0" >"$ENV_FILE"
run --check
check '[[ "$rc" == 0 ]] && has "\"status\":\"disabled\""' "status=disabled"
check '[[ ! -e "$DENY" ]]' "файл не создан"

echo "[test] NGINX_DEFAULT_DENY=0: --apply убирает поставленный сервер по умолчанию и делает reload"
reset
site panel_example_com "$PANEL_CONF"
: >"$ENV_FILE"
run --apply
check '[[ -L "$DENY_LINK" ]]' "без флага сервер по умолчанию стоит"
echo "NGINX_DEFAULT_DENY=false" >"$ENV_FILE"
: >"$FAKE_LOG"
run --apply
check '[[ "$rc" == 0 ]] && has "\"status\":\"disabled\"" && has "\"changed\":true"' "status=disabled, changed=true"
check '[[ ! -e "$DENY" && ! -L "$DENY_LINK" ]]' "файл и ссылка удалены"
check 'grep -q "systemctl reload nginx" "$FAKE_LOG"' "reload"
: >"$FAKE_LOG"
run --apply
check '[[ "$rc" == 0 ]] && has "\"changed\":false" && ! grep -q systemctl "$FAKE_LOG"' "повтор: без изменений и без reload"

echo "[test] NGINX_DEFAULT_DENY из окружения важнее .env (так передаёт панель)"
reset
site panel_example_com "$PANEL_CONF"
echo "NGINX_DEFAULT_DENY=0" >"$ENV_FILE"
rc=0
out="$(NGINX_DEFAULT_DENY=1 bash "$SCRIPT" --check 2>"$TMP/stderr")" || rc=$?
check 'has "\"status\":\"needed\""' "NGINX_DEFAULT_DENY=1 в окружении — needed"
: >"$ENV_FILE"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
