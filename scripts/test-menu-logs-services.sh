#!/usr/bin/env bash
# Подменю журнала (последние строки, в реальном времени, только ошибки с последнего запуска), сброс пароля
# через scripts/reset-password.py и «Сервисы» (только установленные; перезапуск — после [y/N], nginx — после nginx -t).
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CALLS="$TMP/calls.log"
export FAKE_PY="$TMP/py"
mkdir -p "$TMP/units" "$TMP/install"
printf '#!/usr/bin/env bash\necho "py $*" >>"$CALLS"\n' >"$FAKE_PY"
chmod +x "$FAKE_PY"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run <ввод> <код>: journalctl печатает журнал с ошибками (JOURNAL_CLEAN=1 — без), systemctl show — ACTIVE_SINCE,
# list-unit-files знает только nginx.service (NO_NGINX=1 — ничего), nginx -t проходит при NGINX_OK=yes.
run() {
  : >"$CALLS"
  set +e
  printf '%b' "$1" | env -u LC_ALL -u LC_CTYPE LANG=C.UTF-8 INSTALL_DIR="$TMP/install" SYSTEMD_UNIT_DIR="$TMP/units" \
    bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    sleep() { :; }
    timeout() { shift; "$@"; }
    require_root() { :; }
    _menu_python() { echo "$FAKE_PY"; }
    journalctl() {
      echo "journalctl $*" >>"$CALLS"
      if [[ -n "${JOURNAL_CLEAN:-}" ]]; then
        echo "x INFO started"
        return 0
      fi
      printf "%s\n" "x INFO started" "x ERROR boom" "x Traceback (most recent call last):" "x critical: disk full"
    }
    systemctl() {
      case "$1" in
        show) printf "%s\n" "${ACTIVE_SINCE-@1700000000}" ;;
        list-unit-files) if [[ -z "${NO_NGINX:-}" && "$*" == *nginx.service* ]]; then echo "nginx.service enabled enabled"; fi ;;
        is-active) echo active ;;
        *) echo "systemctl $*" >>"$CALLS" ;;
      esac
    }
    nginx() { echo "nginx $*" >>"$CALLS"; [[ "${NGINX_OK:-yes}" == yes ]]; }
    eval "$2"
  ' bash "$ROOT_DIR" "$2" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

calls() { tr '\n' ';' <"$CALLS"; }

echo "[test] последние 50 строк и журнал в реальном времени"
run '' 'unit_logs_tail adminpanelaz-node'
[[ "$(calls)" == "journalctl -u adminpanelaz-node -n 50 --no-pager;" ]] && ok "последние 50" || bad "вызовы: $(calls)"
run '' 'unit_logs_follow adminpanelaz'
[[ "$(calls)" == "journalctl -u adminpanelaz -f -n 20 --no-pager;" ]] && ok "-f -n 20" || bad "вызовы: $(calls)"
grep -q "Ctrl+C" "$TMP/out" && ok "подсказка Ctrl+C" || bad "вывод: $(cat "$TMP/out")"

echo "[test] только ошибки с последнего запуска"
run '' 'unit_logs_errors adminpanelaz'
grep -qF -- "journalctl -u adminpanelaz --since @1700000000 --no-pager -o short-iso" "$CALLS" && ok "--since ActiveEnterTimestamp" \
  || bad "вызовы: $(calls)"
grep -q "x ERROR boom" "$TMP/out" && grep -q "x Traceback" "$TMP/out" && grep -q "x critical: disk full" "$TMP/out" \
  && ok "строки с ошибками" || bad "вывод: $(cat "$TMP/out")"
! grep -q "INFO started" "$TMP/out" && ok "без обычных строк" || bad "обычные строки в выводе"

echo "[test] ошибок нет — «Ошибок нет»"
JOURNAL_CLEAN=1 run '' 'unit_logs_errors adminpanelaz'
grep -q "Ошибок нет" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"

echo "[test] сервис ещё не запускался — ошибки с начала загрузки"
ACTIVE_SINCE="" run '' 'unit_logs_errors adminpanelaz'
grep -qF -- "journalctl -u adminpanelaz -b --no-pager" "$CALLS" && ok "-b" || bad "вызовы: $(calls)"

echo "[test] подменю журнала: заголовок одной строкой, 1, 3, 0"
run '1\n3\n0\n' 'menu_logs adminpanelaz; echo "back"'
grep -qx "Журнал · adminpanelaz" "$TMP/out" && ok "заголовок" || bad "вывод: $(cat "$TMP/out")"
grep -qF "Выберите [0-3, q — назад]: " "$TMP/out" && ok "приглашение" || bad "вывод: $(cat "$TMP/out")"
[[ "$(grep -c '^journalctl' "$CALLS")" -eq 2 ]] && grep -q -- "-n 50" "$CALLS" && grep -q -- "--since" "$CALLS" \
  && ok "последние строки и ошибки" || bad "вызовы: $(calls)"
grep -q "back" "$TMP/out" && ok "0 — назад" || bad "вывод: $(cat "$TMP/out")"
run '9\nq\n' 'menu_logs adminpanelaz; echo "back"'
grep -q "Неверный выбор" "$TMP/out" && grep -q "back" "$TMP/out" && ok "неверный выбор, q — назад" \
  || bad "вывод: $(cat "$TMP/out")"

echo "[test] сброс пароля запускает scripts/reset-password.py без аргументов"
run '' 'menu_action panel_reset_password'
[[ "$(calls)" == "py $ROOT_DIR/scripts/reset-password.py;" ]] && ok "reset-password.py" || bad "вызовы: $(calls)"

echo "[test] ничего не установлено: сообщение и назад"
NO_NGINX=1 run '' 'menu_services; echo "back"'
grep -q "nginx, агенты и DDNS на этом сервере не установлены" "$TMP/out" && grep -q "back" "$TMP/out" \
  && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"

echo "[test] «Сервисы»: только установленные, с состоянием"
touch "$TMP/units/adminpanelaz-node.service" "$TMP/units/adminpanelaz-ddns.timer"
run '' 'neighbor_units'
[[ "$(tr '\n' ' ' <"$TMP/out")" == "nginx adminpanelaz-node adminpanelaz-ddns.timer " ]] && ok "nginx, node, ddns.timer" \
  || bad "список: $(cat "$TMP/out")"
run '0\n' 'menu_services'
grep -qx "  1  nginx                    работает" "$TMP/out" && grep -qx "  3  adminpanelaz-ddns.timer  работает" "$TMP/out" \
  && ok "строки «номер, unit, состояние»" || bad "вывод: $(cat "$TMP/out")"

echo "[test] nginx: [y/N], перезапуск после nginx -t"
run '1\n2\ny\n0\n0\n' 'menu_services'
[[ "$(calls)" == "nginx -t;systemctl restart nginx;" ]] && ok "nginx -t, restart" || bad "вызовы: $(calls)"
grep -qF "Перезапустить nginx? [y/N]: " "$TMP/out" && ok "вопрос [y/N]" || bad "вывод: $(cat "$TMP/out")"
grep -qx "nginx · работает" "$TMP/out" && ok "заголовок «unit · состояние»" || bad "вывод: $(cat "$TMP/out")"

echo "[test] Enter на [y/N] — без перезапуска"
run '1\n2\n\n0\n0\n' 'menu_services'
[[ "$(calls)" == "" ]] && ok "ничего не перезапущено" || bad "вызовы: $(calls)"

echo "[test] nginx -t не прошёл: без перезапуска"
NGINX_OK=no run '1\n2\nд\n0\n0\n' 'menu_services'
[[ "$(calls)" == "nginx -t;" ]] && ok "без restart" || bad "вызовы: $(calls)"
grep -q "nginx -t не прошёл" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"
[[ "$rc" -eq 0 ]] && ok "отказ не закрывает меню" || bad "код $rc"

echo "[test] агент из «Сервисов»: статус и перезапуск"
run '2\n1\n2\nда\n0\n0\n' 'menu_services'
[[ "$(calls)" == "systemctl status adminpanelaz-node --no-pager -l;systemctl restart adminpanelaz-node;" ]] \
  && ok "status, restart" || bad "вызовы: $(calls)"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
