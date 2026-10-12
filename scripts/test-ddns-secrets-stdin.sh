#!/usr/bin/env bash
# Токен DuckDNS и логин/пароль No-IP не должны попадать в аргументы curl: аргументы процесса видит
# любой пользователь сервера (ps, /proc/<pid>/cmdline). Секреты передаются curl конфигурацией через
# stdin (-K -); перевод строки в значении начал бы новую опцию curl — такие значения отклоняются.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export ARGS_LOG="$TMP/args.log" STDIN_LOG="$TMP/stdin.log"

mkdir -p "$TMP/bin"
cat >"$TMP/bin/curl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$ARGS_LOG"
if [[ " $* " == *" -K - "* ]]; then
  cat >>"$STDIN_LOG"
fi
printf '%s\n' "${CURL_REPLY:-OK}"
EOF
chmod +x "$TMP/bin/curl"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run_ddns <ответ провайдера>: ddns-update.sh update с конфигурацией $TMP/ddns.env
run_ddns() {
  : >"$ARGS_LOG"
  : >"$STDIN_LOG"
  set +e
  CURL_REPLY="$1" DDNS_CONFIG="$TMP/ddns.env" PATH="$TMP/bin:$PATH" \
    bash "$ROOT_DIR/scripts/ddns-update.sh" update >"$TMP/out" 2>&1
  rc=$?
  set -e
}

echo "[test] DuckDNS: токен не в аргументах curl, URL — в конфигурации на stdin"
cat >"$TMP/ddns.env" <<'EOF'
DDNS_PROVIDER=duckdns
DDNS_SUBDOMAIN=mypanel
DDNS_TOKEN='tok-SECRET-123'
EOF
run_ddns OK
[[ "$rc" -eq 0 ]] && ok "обновление прошло" || bad "код $rc: $(cat "$TMP/out")"
! grep -q SECRET "$ARGS_LOG" && ok "токена нет в аргументах" || bad "токен в аргументах: $(cat "$ARGS_LOG")"
cat >"$TMP/expected" <<'EOF'
url = "https://www.duckdns.org/update?domains=mypanel&token=tok-SECRET-123&ip="
EOF
diff -u "$TMP/expected" "$STDIN_LOG" >"$TMP/diff" && ok "URL передан через stdin" || bad "stdin: $(cat "$TMP/diff")"

echo "[test] No-IP: логин и пароль не в аргументах curl, кавычки и обратная косая экранированы"
cat >"$TMP/ddns.env" <<'EOF'
DDNS_PROVIDER=noip
DDNS_HOSTNAME=myvpn.ddns.net
DDNS_USERNAME=user@example.com
DDNS_PASSWORD='pa"ss\wo SECRET'
EOF
run_ddns good
[[ "$rc" -eq 0 ]] && ok "обновление прошло" || bad "код $rc: $(cat "$TMP/out")"
! grep -q -e SECRET -e user@example.com "$ARGS_LOG" && ok "логина и пароля нет в аргументах" || bad "секрет в аргументах: $(cat "$ARGS_LOG")"
cat >"$TMP/expected" <<'EOF'
url = "https://dynupdate.no-ip.com/nic/update?hostname=myvpn.ddns.net"
user = "user@example.com:pa\"ss\\wo SECRET"
EOF
diff -u "$TMP/expected" "$STDIN_LOG" >"$TMP/diff" && ok "url и user переданы через stdin" || bad "stdin: $(cat "$TMP/diff")"

echo "[test] перевод строки в пароле No-IP — отказ, curl не вызывается"
printf '%s\n' 'DDNS_PROVIDER=noip' 'DDNS_HOSTNAME=myvpn.ddns.net' 'DDNS_USERNAME=user' \
  "DDNS_PASSWORD=\$'x\\noutput = $TMP/pwned'" >"$TMP/ddns.env"
run_ddns good
[[ "$rc" -ne 0 ]] && ok "отказ" || bad "значение с переводом строки принято"
[[ ! -s "$ARGS_LOG" ]] && ok "curl не вызывался" || bad "curl вызван: $(cat "$ARGS_LOG")"
[[ ! -e "$TMP/pwned" ]] && ok "лишняя опция curl не сработала" || bad "создан $TMP/pwned"
grep -q "перевод строки" "$TMP/out" && ok "понятная ошибка" || bad "нет объяснения: $(cat "$TMP/out")"

echo "[test] перевод строки в токене DuckDNS — отказ, curl не вызывается"
printf '%s\n' 'DDNS_PROVIDER=duckdns' 'DDNS_SUBDOMAIN=mypanel' "DDNS_TOKEN=\$'tok\\nuser = a:b'" >"$TMP/ddns.env"
run_ddns OK
[[ "$rc" -ne 0 ]] && ok "отказ" || bad "значение с переводом строки принято"
[[ ! -s "$ARGS_LOG" ]] && ok "curl не вызывался" || bad "curl вызван: $(cat "$ARGS_LOG")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
