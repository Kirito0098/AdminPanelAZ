#!/usr/bin/env bash
# Шапка меню и --status: пробы (systemctl is-active, curl -m 2 к health) не роняют меню, ошибки — «неизвестно»;
# адрес health строится из backend/.env как site_diagnostics._health_probe_url; ожидание health — до 30 с,
# опрос раз в 2 с; --status — код 0, только если всё установленное работает.
# shellcheck disable=SC2016
set -euo pipefail

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export GIT_CEILING_DIRECTORIES="$TMP"
export CALLS="$TMP/calls.log"
INSTALL="$TMP/install"
mkdir -p "$INSTALL/backend" "$INSTALL/frontend" "$TMP/units"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run <код>: код с подключённым меню. curl успешен начиная с попытки CURL_OK_FROM (0 — никогда); systemctl is-active
# печатает STATE_<unit, - заменён на _>, иначе UNIT_STATE (не задан — active, пустой — пусто); sleep только записывается.
run() {
  : >"$CALLS"
  set +e
  env -u LC_ALL -u LC_CTYPE LANG=C.UTF-8 INSTALL_DIR="$INSTALL" SYSTEMD_UNIT_DIR="$TMP/units" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    curl() {
      echo "curl $*" >>"$CALLS"
      local n
      n="$(grep -c "^curl " "$CALLS")"
      [[ "${CURL_OK_FROM:-0}" -gt 0 && "$n" -ge "${CURL_OK_FROM:-0}" ]]
    }
    sleep() { echo "sleep $*" >>"$CALLS"; }
    timeout() { shift; "$@"; }
    systemctl() {
      local var="STATE_${2//-/_}" state
      state="${!var-${UNIT_STATE-active}}"
      echo "$state"
      [[ "$state" == active ]]
    }
    hostname() { echo "203.0.113.5 10.0.0.1"; }
    eval "$2"
  ' bash "$ROOT_DIR" "$1" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

env_file() { printf '%s\n' "$@" >"$INSTALL/backend/.env"; }

with_units() {
  rm -rf "${TMP:?}/units"
  mkdir -p "$TMP/units"
  local f
  for f in "$@"; do
    touch "$TMP/units/$f"
  done
}

# expect_output <функция> <ожидаемый вывод> <строки .env...>
expect_output() {
  local fn="$1" want="$2"
  shift 2
  env_file "$@"
  run "$fn"
  [[ "$rc" -eq 0 && "$(cat "$TMP/out")" == "$want" ]] && ok "$fn: $want" || bad "$fn: ждали «$want», получено «$(cat "$TMP/out")» (код $rc)"
}

echo "[test] адрес health как в site_diagnostics._health_probe_url"
expect_output panel_health_url "http://127.0.0.1:8000/api/health"
expect_output panel_health_url "http://127.0.0.1:9000/panel/api/health" "BACKEND_PORT=9000" "ACCESS_PATH=panel/"
expect_output panel_health_url "http://127.0.0.1:9000/a/b/api/health" 'BACKEND_PORT="9000"' "ACCESS_PATH=//a//b/"
expect_output panel_health_url "https://127.0.0.1:8443/api/health" "BACKEND_PORT=8443" "USE_HTTPS=true" "SSL_CERT=/etc/ssl/p.pem"
expect_output panel_health_url "http://127.0.0.1:8000/api/health" "USE_HTTPS=true"
expect_output panel_health_url "http://127.0.0.1:7000/api/health" "BACKEND_PORT=1" "BACKEND_PORT=7000"
expect_output panel_health_url "http://127.0.0.1:8100/api/health" "APP_PORT=8100"

echo "[test] адрес панели для браузера"
expect_output panel_public_url "https://panel.example.com/panel/" "DOMAIN=panel.example.com" "BEHIND_NGINX=true" "ACCESS_PATH=/panel"
expect_output panel_public_url "https://panel.example.com:8443/" "DOMAIN=panel.example.com" "BEHIND_NGINX=true" "HTTPS_PUBLIC_PORT=8443"
expect_output panel_public_url "https://panel.example.com:8443/" "DOMAIN=panel.example.com" "USE_HTTPS=true" "SSL_CERT=/x.pem" "BACKEND_PORT=8443"
expect_output panel_public_url "http://203.0.113.5:8000/" "BACKEND_HOST=0.0.0.0"
expect_output panel_public_url "http://203.0.113.5:8000/"
expect_output panel_public_url "http://127.0.0.1:8000/ (только с этого сервера)" "BACKEND_HOST=127.0.0.1"

echo "[test] health: curl с таймаутом 2 с, для https — -k"
env_file
CURL_OK_FROM=1 run 'panel_health_ok'
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc"
grep -qxF "curl -fsS -m 2 -o /dev/null http://127.0.0.1:8000/api/health" "$CALLS" && ok "http" || bad "вызовы: $(cat "$CALLS")"
env_file "USE_HTTPS=true" "SSL_CERT=/x.pem"
CURL_OK_FROM=0 run 'panel_health_ok'
[[ "$rc" -ne 0 ]] && ok "нет ответа — ошибка" || bad "без ответа код 0"
grep -qxF "curl -fsS -m 2 -o /dev/null -k https://127.0.0.1:8000/api/health" "$CALLS" && ok "https -k" || bad "вызовы: $(cat "$CALLS")"

echo "[test] состояние сервиса словом"
for pair in active:работает inactive:остановлен failed:ошибка activating:запускается reloading:запускается \
  "deactivating:неизвестно" ":неизвестно"; do
  UNIT_STATE="${pair%%:*}" run '_menu_unit_state adminpanelaz'
  [[ "$(cat "$TMP/out")" == "${pair#*:}" ]] && ok "«${pair%%:*}» — ${pair#*:}" || bad "${pair%%:*}: $(cat "$TMP/out")"
done
run 'unset -f curl; PATH=/nonexistent; panel_health_state'
[[ "$(cat "$TMP/out")" == "неизвестно" ]] && ok "нет curl — health неизвестно" || bad "без curl: $(cat "$TMP/out")"

echo "[test] строка версии: версия, ветка @ коммит; без git и package.json — «неизвестно»"
printf '{\n  "name": "x",\n  "version": "9.8.7"\n}\n' >"$INSTALL/frontend/package.json"
git -c init.defaultBranch=main init -q "$INSTALL"
git -C "$INSTALL" add -A
git -C "$INSTALL" -c user.email=t@t -c user.name=t commit -qm init
git -C "$INSTALL" checkout -q -b release/9.8.7
short="$(git -C "$INSTALL" rev-parse --short HEAD)"
run 'menu_code_line'
[[ "$(cat "$TMP/out")" == "AdminPanelAZ 9.8.7 · release/9.8.7 @ $short" ]] && ok "версия и ветка@коммит" || bad "вывод: $(cat "$TMP/out")"
rm -rf "$INSTALL"
mkdir -p "$INSTALL/backend"
run 'menu_code_line'
[[ "$rc" -eq 0 && "$(cat "$TMP/out")" == "AdminPanelAZ неизвестно · неизвестно @ неизвестно" ]] && ok "неизвестно" \
  || bad "код $rc: $(cat "$TMP/out")"

echo "[test] --status: код 0, только если всё установленное работает"
env_file
# status_rc <ожидаемый код> <описание>
status_rc() {
  run 'main --status'
  [[ "$rc" -eq "$1" ]] && ok "$2 — код $1" || bad "$2: код $rc, вывод: $(cat "$TMP/out")"
}
with_units adminpanelaz.service
CURL_OK_FROM=1 status_rc 0 "панель работает и отвечает"
grep -qF "Панель   работает · health отвечает" "$TMP/out" && ok "шапка в stdout" || bad "вывод: $(cat "$TMP/out")"
CURL_OK_FROM=0 status_rc 1 "health не отвечает"
CURL_OK_FROM=1 UNIT_STATE=failed status_rc 1 "сервис упал"
with_units adminpanelaz.service adminpanelaz-node.service
CURL_OK_FROM=1 STATE_adminpanelaz_node=failed status_rc 1 "панель и упавший агент"
CURL_OK_FROM=1 status_rc 0 "панель и агент работают"
with_units adminpanelaz-node.service adminpanelaz-proxy.service
STATE_adminpanelaz_proxy=inactive status_rc 1 "один агент из двух остановлен"
grep -qF "Агент    работает (node) · остановлен (proxy)" "$TMP/out" && ok "оба агента в шапке" || bad "вывод: $(cat "$TMP/out")"
! grep -q "curl" "$CALLS" && ok "без панели health не проверяется" || bad "вызовы: $(cat "$CALLS")"
status_rc 0 "агенты работают"
with_units
status_rc 1 "ничего не установлено"
grep -qF "Панель   не установлена через systemd" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"

echo "[test] --status без прав на backend/.env — через sudo, с правами — без"
with_units adminpanelaz.service
CURL_OK_FROM=1 run 'menu_ensure_root() { echo "SUDO $*"; exit 0; }; main --status'
! grep -q "SUDO" "$TMP/out" && ok "читается — без sudo" || bad "вывод: $(cat "$TMP/out")"
run '_menu_can_read() { return 1; }; menu_ensure_root() { echo "SUDO $*"; exit 0; }; main --status'
[[ "$(cat "$TMP/out")" == "SUDO --status" ]] && ok "не читается — sudo --status" || bad "вывод: $(cat "$TMP/out")"

echo "[test] ожидание health: ответ с третьей попытки — два опроса по 2 с"
CURL_OK_FROM=3 run 'panel_wait_health'
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out")"
grep -q "Панель запущена и отвечает" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"
[[ "$(grep -cx 'sleep 2' "$CALLS")" -eq 2 ]] && ok "два sleep 2" || bad "вызовы: $(tr '\n' ';' <"$CALLS")"

echo "[test] панель не отвечает: 16 проб за 30 с, подсказка"
CURL_OK_FROM=0 run 'panel_wait_health'
[[ "$rc" -ne 0 ]] && ok "код ошибки" || bad "код 0"
grep -q "Панель не ответила за 30 с" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"
grep -q "Только ошибки" "$TMP/out" && ok "подсказка про журнал" || bad "нет подсказки: $(cat "$TMP/out")"
[[ "$(grep -cx 'sleep 2' "$CALLS")" -eq 15 && "$(grep -c '^curl ' "$CALLS")" -eq 16 ]] && ok "15 × sleep 2, 16 проб" \
  || bad "вызовы: $(tr '\n' ';' <"$CALLS")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
