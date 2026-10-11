#!/usr/bin/env bash
# Команда adminpanelaz — symlink на меню: через него меню находит свой каталог, без root перезапускается через
# sudo (кроме --help и внутреннего --after-pull), неверный аргумент и меню без терминала — код 2,
# меню открывается по установленным unit'ам systemd.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
MENU="$ROOT_DIR/scripts/adminpanel-menu.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export SUDO_LOG="$TMP/sudo.log"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

mkdir -p "$TMP/link" "$TMP/user-bin" "$TMP/empty-bin" "$TMP/empty-install"
ln -s "$MENU" "$TMP/link/adminpanelaz"
# Обычный пользователь: id -u = 1000, sudo только записывает, с чем и с какой локалью его вызвали.
printf '#!/usr/bin/env bash\necho 1000\n' >"$TMP/user-bin/id"
printf '#!/usr/bin/env bash\necho "sudo $* LC_ALL=[${LC_ALL-}] LANG=[${LANG-}]" >>"$SUDO_LOG"\n' >"$TMP/user-bin/sudo"
chmod +x "$TMP/user-bin/id" "$TMP/user-bin/sudo"

# as_user <аргументы>: меню через symlink от «обычного пользователя»; код в $rc, stdout и stderr — в $TMP/out, $TMP/err
as_user() {
  : >"$SUDO_LOG"
  set +e
  env -u LC_ALL -u NO_COLOR LANG=C PATH="$TMP/user-bin:$PATH" ${USER_NO_COLOR:+NO_COLOR="$USER_NO_COLOR"} \
    "$TMP/link/adminpanelaz" "$@" >"$TMP/out" 2>"$TMP/err"
  rc=$?
  set -e
}

echo "[test] через symlink меню находит свой каталог"
got="$(env -u INSTALL_DIR -u VENV_PATH bash -c 'source "$1"; printf "%s|%s|%s" "$ROOT_DIR" "$INSTALL_DIR" "$BACKUP_CLI"' \
  bash "$TMP/link/adminpanelaz")"
want="$ROOT_DIR|$ROOT_DIR|$ROOT_DIR/scripts/backup-cli.py"
[[ "$got" == "$want" ]] && ok "ROOT_DIR, INSTALL_DIR, BACKUP_CLI" || bad "получено: $got"

# Без рабочего menu_ensure_root `--restart` упирается в require_root (id -u = 1000) — на хосте ничего не делает.
echo "[test] без root: перезапуск через sudo по реальному пути, с теми же аргументами и локалью пользователя"
as_user --restart
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out" "$TMP/err")"
[[ "$(cat "$SUDO_LOG")" == "sudo -- $MENU --restart LC_ALL=[] LANG=[C]" ]] && ok "sudo -- <меню> --restart, LANG=C" \
  || bad "sudo: $(cat "$SUDO_LOG")"

echo "[test] без root с NO_COLOR: sudo получает NO_COLOR (иначе sudo его сбросит)"
USER_NO_COLOR=1 as_user --restart
[[ "$(cat "$SUDO_LOG")" == "sudo NO_COLOR=1 -- $MENU --restart LC_ALL=[] LANG=[C]" ]] && ok "sudo NO_COLOR=1 -- <меню>" \
  || bad "sudo: $(cat "$SUDO_LOG")"

echo "[test] --help работает без root и без sudo, описывает коды выхода"
as_user --help
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/err")"
grep -q "Использование: sudo adminpanelaz" "$TMP/out" && ok "справка про adminpanelaz" || bad "справка: $(cat "$TMP/out")"
grep -q "130  прервано Ctrl+C" "$TMP/out" && ok "коды выхода" || bad "нет кодов выхода: $(cat "$TMP/out")"
[[ ! -s "$SUDO_LOG" ]] && ok "sudo не вызывался" || bad "sudo: $(cat "$SUDO_LOG")"

echo "[test] неизвестный аргумент: сообщение и справка в stderr, код 2, без sudo"
as_user --bogus
[[ "$rc" -eq 2 ]] && ok "код 2" || bad "код $rc"
grep -q "Неизвестный аргумент: --bogus" "$TMP/err" && grep -q "Использование" "$TMP/err" && ok "stderr" \
  || bad "stderr: $(cat "$TMP/err")"
[[ ! -s "$TMP/out" && ! -s "$SUDO_LOG" ]] && ok "stdout пуст, sudo не вызывался" || bad "stdout: $(cat "$TMP/out")"

echo "[test] меню без терминала: справка в stderr, код 2, без sudo"
as_user </dev/null
[[ "$rc" -eq 2 ]] && ok "код 2" || bad "код $rc"
grep -q "Использование" "$TMP/err" && [[ ! -s "$TMP/out" && ! -s "$SUDO_LOG" ]] && ok "справка в stderr" \
  || bad "stdout: $(cat "$TMP/out"), stderr: $(cat "$TMP/err")"

echo "[test] --after-pull (шаг panel_update, уже от root) не перезапускается через sudo"
: >"$SUDO_LOG"
set +e
PATH="$TMP/user-bin:$PATH" INSTALL_DIR="$TMP/empty-install" VENV_PATH="$TMP/no-venv" \
  ADMINPANELAZ_MENU_LINK="$TMP/menu-link/adminpanelaz" "$MENU" --after-pull >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out")"
[[ ! -s "$SUDO_LOG" ]] && ok "sudo не вызывался" || bad "sudo: $(cat "$SUDO_LOG")"

echo "[test] без root и без sudo: «Нужны права root», код 1"
set +e
bash -c 'source "$1"; id() { echo 1000; }; PATH="$2"; main --restart' bash "$MENU" "$TMP/empty-bin" >"$TMP/out" 2>&1
rc=$?
set -e
[[ "$rc" -eq 1 ]] && ok "код 1" || bad "код $rc: $(cat "$TMP/out")"
grep -q "Нужны права root" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"

# with_units <unit-файлы...>: временный каталог unit'ов только с этими файлами
with_units() {
  rm -rf "${TMP:?}/units"
  mkdir -p "$TMP/units"
  local f
  for f in "$@"; do
    touch "$TMP/units/$f"
  done
}
mode_of() {
  with_units "$@"
  SYSTEMD_UNIT_DIR="$TMP/units" bash -c 'source "$1"; menu_mode' bash "$MENU"
}

echo "[test] режим по unit'ам: panel / agent / both / none"
[[ "$(mode_of adminpanelaz.service)" == panel ]] && ok "панель" || bad "панель: $(mode_of adminpanelaz.service)"
[[ "$(mode_of adminpanelaz-node.service)" == agent ]] && ok "node agent" || bad "node agent"
[[ "$(mode_of adminpanelaz-proxy.service)" == agent ]] && ok "proxy agent" || bad "proxy agent"
[[ "$(mode_of adminpanelaz.service adminpanelaz-proxy.service)" == both ]] && ok "панель и агент" || bad "панель и агент"
[[ "$(mode_of)" == none ]] && ok "ничего" || bad "ничего: $(mode_of)"

# start_menu <unit-файлы...>: menu_start с заглушкой main_menu; код в $rc, вывод в $TMP/out
start_menu() {
  with_units "$@"
  set +e
  SYSTEMD_UNIT_DIR="$TMP/units" bash -c '
    set -euo pipefail
    source "$1"
    main_menu() { echo "MAIN MENU $*"; }
    menu_start
  ' bash "$MENU" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

echo "[test] ничего не установлено: сообщение, справка, код 1"
start_menu
[[ "$rc" -eq 1 ]] && ok "код 1" || bad "код $rc"
grep -q "AdminPanelAZ не установлена через systemd" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"
grep -q "Использование" "$TMP/out" && ok "справка" || bad "нет справки"
! grep -q "MAIN MENU" "$TMP/out" && ok "меню не открыто" || bad "меню открыто"

echo "[test] панель установлена: главное меню в режиме panel"
start_menu adminpanelaz.service
[[ "$rc" -eq 0 ]] && grep -q "MAIN MENU panel" "$TMP/out" && ok "главное меню" || bad "код $rc: $(cat "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
