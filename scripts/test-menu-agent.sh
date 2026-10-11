#!/usr/bin/env bash
# Меню агента узла: на сервере только с агентом открывается вместо меню панели, на сервере с панелью — пунктом 9.
# Пункты 1/2/4/5 при двух агентах (node и proxy) сначала спрашивают, какой; перезапуск проверяется через 5 с,
# mTLS — как в install.sh, обновление — panel_update и вопрос [Y/n] о перезапуске выбранного агента.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CALLS="$TMP/calls.log"
export GIT_CEILING_DIRECTORIES="$TMP"
INSTALL="$TMP/install"
mkdir -p "$INSTALL/backend" "$TMP/mtls"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

with_units() {
  rm -rf "${TMP:?}/units"
  mkdir -p "$TMP/units"
  local f
  for f in "$@"; do
    touch "$TMP/units/$f"
  done
}

# run <ввод> <код>: systemctl is-active печатает STATE (по умолчанию active), остальные вызовы systemctl и sleep
# записываются; UPDATE_RESULT=changed|same — итог panel_update.
run() {
  : >"$CALLS"
  set +e
  printf '%b' "$1" | env -u LC_ALL -u LC_CTYPE LANG=C.UTF-8 INSTALL_DIR="$INSTALL" SYSTEMD_UNIT_DIR="$TMP/units" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    timeout() { shift; "$@"; }
    require_root() { :; }
    sleep() { echo "sleep $*" >>"$CALLS"; }
    systemctl() {
      case "$1" in
        is-active) echo "${STATE:-active}"; [[ "${STATE:-active}" == active ]] ;;
        *) echo "systemctl $*" >>"$CALLS" ;;
      esac
    }
    journalctl() { echo "journalctl $*" >>"$CALLS"; }
    curl() { return 0; }
    panel_update() {
      echo "panel_update" >>"$CALLS"
      if [[ "${UPDATE_RESULT:-same}" == changed ]]; then PANEL_UPDATE_CHANGED=true; fi
    }
    eval "$2"
  ' bash "$ROOT_DIR" "$2" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

calls() { tr '\n' ';' <"$CALLS"; }
# Действия меню агента — заглушки, которые записывают, с каким агентом их вызвали.
STUBS='for fn in agent_update agent_restart agent_mtls_check unit_status menu_logs menu_full_update; do
    eval "$fn() { echo \"$fn \$*\" >>\"\$CALLS\"; }"
  done; '

echo "[test] сервер только с агентом: меню агента вместо меню панели"
with_units adminpanelaz-node.service
run '' 'main_menu() { echo "MAIN MENU"; }; menu_agent() { echo "AGENT MENU $*"; }; menu_start'
grep -q "AGENT MENU top" "$TMP/out" && ! grep -q "MAIN MENU" "$TMP/out" && ok "menu_agent top" || bad "вывод: $(cat "$TMP/out")"

echo "[test] один агент: пункты 1–5 без вопроса «какой», 6 — полное обновление"
run '1\n2\n3\n4\n5\n6\n0\n' "$STUBS"'menu_agent; echo "back"'
[[ "$(calls)" == "agent_update adminpanelaz-node;menu_logs adminpanelaz-node;agent_mtls_check ;agent_restart adminpanelaz-node;unit_status adminpanelaz-node;menu_full_update ;" ]] \
  && ok "1–6 для node" || bad "вызовы: $(calls)"
! grep -q "Какой агент" "$TMP/out" && ok "без вопроса" || bad "вывод: $(cat "$TMP/out")"
grep -q "back" "$TMP/out" && grep -qx "  0  Назад" "$TMP/out" && ok "0 — назад" || bad "вывод: $(cat "$TMP/out")"
grep -qF "Выберите [0-6, q — назад]: " "$TMP/out" && ok "приглашение" || bad "вывод: $(cat "$TMP/out")"

echo "[test] два агента: 1/2/4/5 спрашивают, какой; 3 — нет"
with_units adminpanelaz-node.service adminpanelaz-proxy.service
run '4\n2\n5\n1\n3\n1\n0\n0\n' "$STUBS"'menu_agent'
[[ "$(calls)" == "agent_restart adminpanelaz-proxy;unit_status adminpanelaz-node;agent_mtls_check ;" ]] \
  && ok "4 → proxy, 5 → node, 3 без вопроса, 1 → 0 — назад" || bad "вызовы: $(calls)"
grep -q "^Какой агент?$" "$TMP/out" && grep -qx "  1  node" "$TMP/out" && grep -qx "  2  proxy" "$TMP/out" \
  && ok "вопрос «Какой агент?»" || bad "вывод: $(cat "$TMP/out")"
run '2\n7\n0\n' "$STUBS"'menu_agent'
[[ "$(calls)" == "sleep 1;" ]] && grep -q "Неверный выбор" "$TMP/out" && ok "неверный номер агента — только пауза" \
  || bad "вызовы: $(calls)"

echo "[test] меню агента без панели: 0 и q — выход с кодом 0"
with_units adminpanelaz-node.service
for key in 0 q; do
  run "$key\n" 'menu_agent top; echo "after"'
  [[ "$rc" -eq 0 ]] && ! grep -q "after" "$TMP/out" && grep -qx "  0  Выход" "$TMP/out" && ok "«$key» — exit 0" \
    || bad "код $rc: $(cat "$TMP/out")"
done

echo "[test] перезапуск агента: restart, через 5 с — проверка"
run '' 'agent_restart adminpanelaz-node'
[[ "$(calls)" == "systemctl restart adminpanelaz-node;sleep 5;" ]] && ok "restart, sleep 5" || bad "вызовы: $(calls)"
grep -q "adminpanelaz-node работает" "$TMP/out" && ok "работает" || bad "вывод: $(cat "$TMP/out")"
STATE=failed run '' 'agent_restart adminpanelaz-node'
[[ "$rc" -eq 1 ]] && grep -q "adminpanelaz-node не запустился" "$TMP/out" && ok "не запустился, код 1" \
  || bad "код $rc: $(cat "$TMP/out")"

echo "[test] обновление агента: вопрос [Y/n] только после обновления, перезапуск выбранного"
with_units adminpanelaz-node.service adminpanelaz-proxy.service
UPDATE_RESULT=changed run '\n' 'agent_update adminpanelaz-proxy'
[[ "$(calls)" == "panel_update;systemctl restart adminpanelaz-proxy;sleep 5;" ]] && ok "update, restart proxy" \
  || bad "вызовы: $(calls)"
grep -qF "Перезапустить adminpanelaz-proxy сейчас? [Y/n]: " "$TMP/out" && ok "вопрос" || bad "вывод: $(cat "$TMP/out")"
UPDATE_RESULT=changed run 'n\n' 'agent_update adminpanelaz-proxy'
[[ "$(calls)" == "panel_update;" ]] && grep -q "Агент не перезапущен" "$TMP/out" && ok "n — без перезапуска" \
  || bad "вызовы: $(calls)"
UPDATE_RESULT=same run '\n' 'agent_update adminpanelaz-proxy'
[[ "$(calls)" == "panel_update;" ]] && ! grep -q "Перезапустить" "$TMP/out" && ok "без обновлений — без вопроса" \
  || bad "вызовы: $(calls)"

echo "[test] mTLS: только proxy — сообщение; node — как в install.sh"
with_units adminpanelaz-proxy.service
run '' 'agent_mtls_check'
[[ "$rc" -eq 0 ]] && grep -q "mTLS проверяется для node agent — на этом сервере его нет" "$TMP/out" && ok "proxy" \
  || bad "код $rc: $(cat "$TMP/out")"
with_units adminpanelaz-node.service
printf 'NODE_AGENT_MTLS_ENABLED=true\nNODE_AGENT_MTLS_CA_CERT=%s\nNODE_AGENT_MTLS_SERVER_CERT=%s\nNODE_AGENT_MTLS_SERVER_KEY=%s\n' \
  "$TMP/mtls/ca.crt" "$TMP/mtls/agent.crt" "$TMP/mtls/agent.key" >"$INSTALL/backend/node_agent.env"
run '' 'menu_action agent_mtls_check; echo "menu alive"'
grep -q "сертификатов нет" "$TMP/out" && ok "предупреждение" || bad "вывод: $(cat "$TMP/out")"
grep -q "menu alive" "$TMP/out" && ok "меню продолжает работу" || bad "меню закрылось"
touch "$TMP/mtls/ca.crt" "$TMP/mtls/agent.crt" "$TMP/mtls/agent.key"
run '' 'agent_mtls_check'
grep -q "mTLS включён, сертификаты на месте" "$TMP/out" && ok "сертификаты на месте" || bad "вывод: $(cat "$TMP/out")"
printf 'NODE_AGENT_MTLS_ENABLED=false\n' >"$INSTALL/backend/node_agent.env"
run '' 'agent_mtls_check'
grep -q "mTLS выключен" "$TMP/out" && ok "выключен" || bad "вывод: $(cat "$TMP/out")"

echo "[test] панель и агент: пункт 9 «Агент узла» открывает меню агента"
with_units adminpanelaz.service adminpanelaz-node.service
run '9\nq\n' 'menu_agent() { echo "agent_menu $*" >>"$CALLS"; }; main_menu both'
[[ "$rc" -eq 0 && "$(calls)" == "agent_menu ;" ]] && ok "пункт 9" || bad "код $rc, вызовы: $(calls)"
grep -qF "Выберите [0-10, q — выход]: " "$TMP/out" && ok "приглашение [0-10]" || bad "вывод: $(cat "$TMP/out")"

echo "[test] панель и агент: пункт 10 — полное обновление"
run '10\nq\n' 'menu_full_update() { echo "full_update" >>"$CALLS"; }; main_menu both'
[[ "$rc" -eq 0 && "$(calls)" == "full_update;" ]] && ok "пункт 10" || bad "код $rc, вызовы: $(calls)"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
