#!/usr/bin/env bash
# No-IP отвечает «good <IP>» / «nochg <IP>»: успех определяется по первому слову ответа.
# Раньше из ответа удалялись все пробелы, получалось «good203.0.113.7» и ошибка «неожиданный ответ».
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/bin"
cat >"$TMP/bin/curl" <<'EOF'
#!/usr/bin/env bash
cat >/dev/null
printf '%s\n' "$CURL_REPLY"
EOF
chmod +x "$TMP/bin/curl"

cat >"$TMP/ddns.env" <<'EOF'
DDNS_PROVIDER=noip
DDNS_HOSTNAME=myvpn.ddns.net
DDNS_USERNAME=user
DDNS_PASSWORD=pass
EOF

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run_noip <ответ No-IP>: ddns-update.sh update с подменённым curl
run_noip() {
  set +e
  CURL_REPLY="$1" DDNS_CONFIG="$TMP/ddns.env" PATH="$TMP/bin:$PATH" \
    bash "$ROOT_DIR/scripts/ddns-update.sh" update >"$TMP/out" 2>&1
  rc=$?
  set -e
}

for reply in "good 203.0.113.7" "nochg 203.0.113.7" "good" $'good 203.0.113.7\r'; do
  echo "[test] ответ «${reply%$'\r'}» — успех"
  run_noip "$reply"
  [[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out")"
  grep -q "myvpn.ddns.net обновлён" "$TMP/out" && ok "сообщение об обновлении" || bad "вывод: $(cat "$TMP/out")"
done

echo "[test] badauth — понятная ошибка"
run_noip "badauth"
[[ "$rc" -ne 0 ]] && ok "отказ" || bad "badauth принят"
grep -q "неверный логин или пароль" "$TMP/out" && ok "сообщение badauth" || bad "вывод: $(cat "$TMP/out")"

for reply in "goodbye" "nochgx 203.0.113.7" "911"; do
  echo "[test] ответ «$reply» — неожиданный"
  run_noip "$reply"
  [[ "$rc" -ne 0 ]] && ok "отказ" || bad "ответ «$reply» принят как успех"
  grep -qF "неожиданный ответ: $reply" "$TMP/out" && ok "ответ в сообщении" || bad "вывод: $(cat "$TMP/out")"
done

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
