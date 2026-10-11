#!/usr/bin/env bash
# В интерактивном меню после обновления (код обновлён или интерфейс пересобран) меню спрашивает о перезапуске
# ([Y/n], Enter — да), перезапускает панель и ждёт /api/health; без обновлений не спрашивает; --update из командной
# строки — как раньше, без вопроса.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CALLS="$TMP/calls.log"
mkdir -p "$TMP/units" "$TMP/install"
touch "$TMP/units/adminpanelaz.service"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run <ввод> <код>: UPDATE_RESULT=changed|same|fail задаёт итог panel_update, CURL_OK=yes|no — ответ health.
run() {
  : >"$CALLS"
  set +e
  printf '%b' "$1" | env -u LC_ALL -u LC_CTYPE LANG=C.UTF-8 INSTALL_DIR="$TMP/install" SYSTEMD_UNIT_DIR="$TMP/units" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    require_root() { :; }
    menu_ensure_root() { :; }
    panel_update() {
      echo "panel_update" >>"$CALLS"
      case "${UPDATE_RESULT:-same}" in
        changed) PANEL_UPDATE_CHANGED=true ;;
        fail) return 1 ;;
      esac
    }
    systemctl() { echo "systemctl $*" >>"$CALLS"; }
    curl() { echo "curl" >>"$CALLS"; [[ "${CURL_OK:-yes}" == yes ]]; }
    sleep() { :; }
    eval "$2"
  ' bash "$ROOT_DIR" "$2" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

calls() { tr '\n' ';' <"$CALLS"; }
INTERACTIVE='menu_action panel_update_interactive; echo "menu alive"'

echo "[test] обновление есть, Enter: перезапуск и ожидание health"
UPDATE_RESULT=changed run '\n' "$INTERACTIVE"
[[ "$(calls)" == "panel_update;systemctl restart adminpanelaz;curl;" ]] && ok "update, restart, health" || bad "вызовы: $(calls)"
grep -qF "Перезапустить панель сейчас? [Y/n]: " "$TMP/out" && ok "вопрос [Y/n]" || bad "нет вопроса: $(cat "$TMP/out")"
grep -q "Панель запущена и отвечает" "$TMP/out" && ok "панель отвечает" || bad "вывод: $(cat "$TMP/out")"
grep -q "menu alive" "$TMP/out" && ok "меню продолжает работу" || bad "меню закрылось"

echo "[test] ответы «да» и «Y» тоже перезапускают"
for answer in да Y; do
  UPDATE_RESULT=changed run "$answer\n" "$INTERACTIVE"
  grep -q "systemctl restart adminpanelaz" "$CALLS" && ok "«$answer» — перезапуск" || bad "«$answer»: вызовы $(calls)"
done

echo "[test] ответ n: без перезапуска, с подсказкой"
UPDATE_RESULT=changed run 'n\n' "$INTERACTIVE"
[[ "$(calls)" == "panel_update;" ]] && ok "только update" || bad "вызовы: $(calls)"
grep -q "Панель не перезапущена" "$TMP/out" && ok "подсказка" || bad "вывод: $(cat "$TMP/out")"

echo "[test] конец ввода на вопросе: без перезапуска"
UPDATE_RESULT=changed run '' "$INTERACTIVE"
[[ "$(calls)" == "panel_update;" ]] && ok "только update" || bad "вызовы: $(calls)"

echo "[test] обновлений нет: вопроса нет"
UPDATE_RESULT=same run '\n' "$INTERACTIVE"
[[ "$(calls)" == "panel_update;" ]] && ok "только update" || bad "вызовы: $(calls)"
! grep -q "Перезапустить панель сейчас" "$TMP/out" && ok "без вопроса" || bad "вопрос задан без обновления"

echo "[test] обновление не удалось: вопроса нет, меню живо"
UPDATE_RESULT=fail run '\n' "$INTERACTIVE"
[[ "$(calls)" == "panel_update;" ]] && ok "только update" || bad "вызовы: $(calls)"
grep -q "menu alive" "$TMP/out" && ok "меню продолжает работу" || bad "меню закрылось"

echo "[test] панель не ответила за 30 с: подсказка, меню живо"
UPDATE_RESULT=changed CURL_OK=no run '\n' "$INTERACTIVE"
grep -q "Панель не ответила за 30 с" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"
grep -q "menu alive" "$TMP/out" && ok "меню продолжает работу" || bad "меню закрылось"

echo "[test] --update из командной строки не спрашивает"
UPDATE_RESULT=changed run '\n' 'main --update'
[[ "$rc" -eq 0 && "$(calls)" == "panel_update;" ]] && ok "только update" || bad "код $rc, вызовы: $(calls)"
! grep -q "Перезапустить панель сейчас" "$TMP/out" && ok "без вопроса" || bad "--update задал вопрос"

echo "[test] «Перезапустить панель» ждёт health и ни о чём не спрашивает"
run '' 'menu_action panel_restart_and_wait'
[[ "$(calls)" == "systemctl restart adminpanelaz;curl;" ]] && ok "restart, health" || bad "вызовы: $(calls)"
! grep -q "\[y/N\]\|\[Y/n\]" "$TMP/out" && ok "без вопроса" || bad "вопрос: $(cat "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
