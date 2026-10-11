#!/usr/bin/env bash
# Меню в настоящем терминале (псевдотерминал через script из util-linux): цвет только без NO_COLOR и не при
# TERM=dumb; Ctrl+C в меню — выход с кодом 130 и переводом строки; Ctrl+C в журнале реального времени — назад в меню.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
INSTALL="$TMP/install"
mkdir -p "$INSTALL/backend" "$TMP/units"
touch "$TMP/units/adminpanelaz.service"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# Сценарий внутри псевдотерминала: меню с подменёнными пробами и журналом, затем код из переменной CODE.
cat >"$TMP/drive.sh" <<'EOF'
set -euo pipefail
source "$MENU_ROOT/scripts/adminpanel-menu.sh"
timeout() { shift; "$@"; }
systemctl() { echo active; }
curl() { return 0; }
git() { return 1; }
sleep() { :; }
journalctl() {
  echo follow >"$MARK_DIR/following"
  command sleep 30
}
eval "$CODE"
EOF

# pty <ввод> <код> [переменные окружения...]: код в псевдотерминале; <ввод> — функция, которая печатает нажатия
# (или «-» — без ввода). NO_COLOR, TERM и локаль снаружи не наследуются. Вывод в $TMP/out, код в $rc.
pty() {
  local feed="$1" code="$2"
  shift 2
  [[ "$feed" != - ]] || feed=true
  set +e
  "$feed" | env -u NO_COLOR -u TERM -u LC_ALL -u LC_CTYPE LANG=C.UTF-8 "$@" CODE="$code" MENU_ROOT="$ROOT_DIR" \
    MARK_DIR="$TMP" INSTALL_DIR="$INSTALL" SYSTEMD_UNIT_DIR="$TMP/units" COLUMNS=80 \
    script -qefc "bash $TMP/drive.sh" /dev/null >"$TMP/out" 2>&1
  rc=$?
  set -e
}

# wait_for <файл> <строка> [сколько раз]: дождаться (до 10 с), пока в файле не появится строка
wait_for() {
  local i
  for ((i = 0; i < 100; i++)); do
    if [[ -e "$1" && "$(grep -cF -- "$2" "$1" 2>/dev/null)" -ge "${3:-1}" ]]; then
      return 0
    fi
    sleep 0.1
  done
  echo "  не дождались «$2» в $1" >&2
  return 1
}

echo "[test] --status в терминале: цвет есть, при NO_COLOR и TERM=dumb — нет"
pty - 'main --status' TERM=xterm
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat -v "$TMP/out")"
grep -q $'\033\\[' "$TMP/out" && ok "TERM=xterm — цвет" || bad "нет цвета: $(cat -v "$TMP/out")"
grep -q "работает" "$TMP/out" && ok "состояние словом" || bad "вывод: $(cat "$TMP/out")"
pty - 'main --status' TERM=xterm NO_COLOR=1
! grep -q $'\033' "$TMP/out" && ok "NO_COLOR=1 — без \\033" || bad "есть \\033: $(cat -v "$TMP/out")"
pty - 'main --status' TERM=dumb
! grep -q $'\033' "$TMP/out" && ok "TERM=dumb — без \\033" || bad "есть \\033: $(cat -v "$TMP/out")"

echo "[test] главное меню в терминале при NO_COLOR=1 — без \\033"
pty - 'menu_probe panel; menu_render_main panel' TERM=xterm NO_COLOR=1
grep -q "Обновить и перезапустить" "$TMP/out" && ! grep -q $'\033' "$TMP/out" && ok "без \\033" \
  || bad "вывод: $(cat -v "$TMP/out")"

echo "[test] Ctrl+C в главном меню — код 130 и перевод строки"
press_ctrl_c_at_menu() {
  wait_for "$TMP/out" "Выберите [0-8"
  printf '\003'
  sleep 1
}
pty press_ctrl_c_at_menu 'menu_start' TERM=xterm NO_COLOR=1
[[ "$rc" -eq 130 ]] && ok "код 130" || bad "код $rc: $(cat -v "$TMP/out")"
[[ "$(tail -c 1 "$TMP/out" | od -An -c | tr -d ' ')" == '\n' ]] && ok "вывод кончается переводом строки" \
  || bad "конец вывода: $(tail -c 20 "$TMP/out" | od -An -c)"

# Псевдотерминал сбрасывает непрочитанный ввод по Ctrl+C, поэтому следующие нажатия — после маркеров в выводе.
echo "[test] Ctrl+C в журнале реального времени — назад в меню, меню работает дальше"
rm -f "$TMP/following"
follow_then_ctrl_c() {
  wait_for "$TMP/out" "Выберите [0-8"
  printf '2\n'
  wait_for "$TMP/out" "Последние 50 строк"
  printf '2\n'
  wait_for "$TMP/following" follow
  printf '\003'
  wait_for "$TMP/out" "Нажмите Enter"
  printf '\n'
  wait_for "$TMP/out" "Последние 50 строк" 2
  printf '0\n'
  wait_for "$TMP/out" "Выберите [0-8" 2
  printf 'q\n'
  sleep 1
}
pty follow_then_ctrl_c 'menu_start' TERM=xterm NO_COLOR=1
[[ "$rc" -eq 0 ]] && ok "выход из меню по q — код 0" || bad "код $rc: $(cat -v "$TMP/out")"
grep -q "в реальном времени. Ctrl+C" "$TMP/out" && ok "подсказка Ctrl+C" || bad "вывод: $(cat -v "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
