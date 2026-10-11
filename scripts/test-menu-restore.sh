#!/usr/bin/env bash
# Восстановление из меню, порядок владельца: выбор из backup-cli.py list → предупреждение → ввод «да» → копия
# текущего состояния (create --no-prune; не создалась — стоп) → restore выбранного архива → ожидание health.
# Отмена ничего не создаёт и ничего не останавливает.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CALLS="$TMP/calls.log"
export FAKE_PY="$TMP/py"
SAFETY=/var/backups/adminpanelaz/adminpanelaz_safety.tar.gz
mkdir -p "$TMP/install"

# Подмена python: первый аргумент — путь backup-cli.py, дальше — подкоманда.
cat >"$FAKE_PY" <<'EOF'
#!/usr/bin/env bash
shift
echo "cli $*" >>"$CALLS"
case "$1" in
  list)
    [[ -n "${NO_BACKUPS:-}" ]] || printf '%s\t%s\t%s\t%s\n' \
      adminpanelaz_new.tar.gz 2026-10-11T08:00:00Z 3145728 db,env,configs \
      adminpanelaz_old.tar.gz 2026-10-01T08:00:00Z 1048576 db
    ;;
  create)
    if [[ -n "${CREATE_FAILS:-}" ]]; then
      echo "ERROR: диск заполнен" >&2
      exit 1
    fi
    echo /var/backups/adminpanelaz/adminpanelaz_safety.tar.gz
    ;;
  restore)
    [[ -z "${RESTORE_FAILS:-}" ]] || exit 1
    echo "$2"
    ;;
esac
EOF
chmod +x "$FAKE_PY"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run <ввод>: panel_restore внутри menu_action, health отвечает сразу; systemctl записывается
run() {
  : >"$CALLS"
  set +e
  printf '%b' "$1" | env -u LC_ALL -u LC_CTYPE LANG=C.UTF-8 INSTALL_DIR="$TMP/install" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    require_root() { :; }
    _menu_python() { echo "$FAKE_PY"; }
    systemctl() { echo "systemctl $*" >>"$CALLS"; }
    curl() { return 0; }
    sleep() { :; }
    menu_action panel_restore
    echo "menu alive"
  ' bash "$ROOT_DIR" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

calls() { tr '\n' ';' <"$CALLS"; }

echo "[test] список: дата, размер в МБ, состав; 0 — отмена"
run '0\n'
grep -qx "  1  2026-10-11 08:00:00 UTC · 3.0 МБ · база, .env, списки AntiZapret" "$TMP/out" && ok "первая строка" \
  || bad "вывод: $(cat "$TMP/out")"
grep -qx "  2  2026-10-01 08:00:00 UTC · 1.0 МБ · база" "$TMP/out" && ok "вторая строка" || bad "вывод: $(cat "$TMP/out")"
grep -qx "  0  Отмена" "$TMP/out" && grep -qF "Выберите [0-2, q — отмена]: " "$TMP/out" && ok "0 — отмена" \
  || bad "вывод: $(cat "$TMP/out")"
[[ "$(calls)" == "cli list;" ]] && ok "только list" || bad "вызовы: $(calls)"
grep -q "Восстановление отменено" "$TMP/out" && ok "отмена" || bad "вывод: $(cat "$TMP/out")"

echo "[test] без «да»: ничего не создано и не остановлено"
for answer in нет Да; do
  run "1\n$answer\n"
  [[ "$(calls)" == "cli list;" ]] && ok "«$answer» — только list" || bad "«$answer»: вызовы $(calls)"
  grep -q "Восстановление отменено, ничего не изменено" "$TMP/out" && ok "«$answer» — сообщение" \
    || bad "вывод: $(cat "$TMP/out")"
done
grep -q "Панель будет остановлена" "$TMP/out" && grep -q "будет сделана копия текущего состояния" "$TMP/out" \
  && ok "предупреждение до вопроса" || bad "нет предупреждения: $(cat "$TMP/out")"
grep -qF "Восстановить из adminpanelaz_new.tar.gz? Введите «да»: " "$TMP/out" && ok "вопрос" || bad "вывод: $(cat "$TMP/out")"

echo "[test] конец ввода на подтверждении: отмена"
run '1\n'
[[ "$(calls)" == "cli list;" ]] && ok "только list" || bad "вызовы: $(calls)"

echo "[test] копия текущего состояния не создалась: стоп, restore нет"
CREATE_FAILS=1 run '1\nда\n'
[[ "$(calls)" == "cli list;cli create --no-prune;" ]] && ok "без restore" || bad "вызовы: $(calls)"
grep -q "восстановление отменено, панель не останавливалась" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"
grep -q "menu alive" "$TMP/out" && ok "меню продолжает работу" || bad "меню закрылось"

echo "[test] «да»: create --no-prune, затем restore выбранного архива, health, имя копии"
run '2\nда\n'
[[ "$(calls)" == "cli list;cli create --no-prune;cli restore adminpanelaz_old.tar.gz;" ]] && ok "list → create → restore" \
  || bad "вызовы: $(calls)"
grep -q "Восстановлено из adminpanelaz_old.tar.gz" "$TMP/out" && ok "итог" || bad "вывод: $(cat "$TMP/out")"
grep -qF "Копия состояния до восстановления: $SAFETY" "$TMP/out" && ok "имя копии" || bad "вывод: $(cat "$TMP/out")"
grep -q "Панель запущена и отвечает" "$TMP/out" && ok "health" || bad "вывод: $(cat "$TMP/out")"
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc"

echo "[test] restore не удался: имя копии в сообщении"
RESTORE_FAILS=1 run '1\nда\n'
grep -qF "Восстановление не удалось. Копия состояния до восстановления: $SAFETY" "$TMP/out" && ok "сообщение" \
  || bad "вывод: $(cat "$TMP/out")"

echo "[test] резервных копий нет"
NO_BACKUPS=1 run '1\n'
[[ "$(calls)" == "cli list;" ]] && ok "только list" || bad "вызовы: $(calls)"
grep -q "Резервных копий нет" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"

echo "[test] номер вне списка"
for choice in 9 01 x; do
  run "$choice\n"
  [[ "$(calls)" == "cli list;" ]] && grep -q "Неверный выбор" "$TMP/out" && ok "«$choice» — неверный выбор" \
    || bad "«$choice»: вызовы $(calls), вывод $(cat "$TMP/out")"
done

echo "[test] «Бэкап и восстановление»: 1 — создать, 2 — восстановить"
: >"$CALLS"
printf '1\n2\n0\n' | env -u LC_ALL -u LC_CTYPE LANG=C.UTF-8 bash -c '
  source "$1/scripts/adminpanel-menu.sh"
  panel_backup() { echo "backup $*" >>"$CALLS"; }
  panel_restore() { echo "restore $*" >>"$CALLS"; }
  menu_backups
' bash "$ROOT_DIR" >"$TMP/out" 2>&1
[[ "$(calls)" == "backup ;restore ;" ]] && ok "создать, восстановить" || bad "вызовы: $(calls)"
grep -qx "Бэкап и восстановление" "$TMP/out" && ok "заголовок" || bad "вывод: $(cat "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
