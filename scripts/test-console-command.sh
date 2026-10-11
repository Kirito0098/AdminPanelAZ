#!/usr/bin/env bash
# Команда adminpanelaz: install.sh и шаг меню после обновления ставят symlink на меню (чужой файл не трогают),
# uninstall.sh удаляет только ссылку на свой каталог. Путь ссылки подменён — /usr/local/bin не трогается.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
LINK="$TMP/bin/adminpanelaz"
export ADMINPANELAZ_MENU_LINK="$LINK"
INSTALL="$TMP/install"
OTHER="$TMP/other"
for dir in "$INSTALL" "$OTHER"; do
  mkdir -p "$dir/scripts"
  cp "$ROOT_DIR/scripts/adminpanel-menu.sh" "$ROOT_DIR/scripts/console-command.sh" "$dir/scripts/"
done

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

extract() { sed -n "/^${2}() {/,/^}/p" "$1"; }

# lib <код>: код с подключённой библиотекой; код возврата в $rc
lib() {
  set +e
  INSTALL="$INSTALL" OTHER="$OTHER" bash -c 'set -euo pipefail; source "$1"; eval "$2"' \
    bash "$ROOT_DIR/scripts/console-command.sh" "$1" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

echo "[test] ссылка создаётся вместе с каталогом и переставляется на текущую установку"
lib 'console_command_link "$INSTALL"'
[[ "$rc" -eq 0 && "$(readlink "$LINK")" == "$INSTALL/scripts/adminpanel-menu.sh" ]] && ok "создана" || bad "код $rc, $(readlink "$LINK" || true)"
lib 'console_command_link "$INSTALL"'
[[ "$rc" -eq 0 ]] && ok "повторно — без ошибки" || bad "код $rc"
lib 'console_command_link "$OTHER"; console_command_link "$INSTALL"'
[[ "$(readlink "$LINK")" == "$INSTALL/scripts/adminpanel-menu.sh" ]] && ok "переставлена" || bad "$(readlink "$LINK")"

echo "[test] чужой файл на месте ссылки не перезаписывается"
rm -f "$LINK"
echo "#!/bin/sh" >"$LINK"
lib 'console_command_link "$INSTALL"'
[[ "$rc" -eq 2 && ! -L "$LINK" && "$(cat "$LINK")" == "#!/bin/sh" ]] && ok "код 2, файл цел" || bad "код $rc"
rm -f "$LINK"

echo "[test] удаление: только ссылка на свой каталог"
ln -s "$OTHER/scripts/adminpanel-menu.sh" "$LINK"
lib 'console_command_unlink "$INSTALL"'
[[ "$rc" -eq 1 && -L "$LINK" ]] && ok "ссылка в другой каталог осталась" || bad "код $rc"
ln -sfn "$INSTALL/scripts/adminpanel-menu.sh" "$LINK"
lib 'console_command_unlink "$INSTALL"'
[[ "$rc" -eq 0 && ! -e "$LINK" && ! -L "$LINK" ]] && ok "своя ссылка удалена" || bad "код $rc"
lib 'console_command_unlink "$INSTALL"'
[[ "$rc" -eq 1 ]] && ok "нечего удалять — код 1" || bad "код $rc"
echo "#!/bin/sh" >"$LINK"
lib 'console_command_unlink "$INSTALL"'
[[ "$rc" -eq 1 && -f "$LINK" ]] && ok "чужой файл не удалён" || bad "код $rc"
rm -f "$LINK"

# install_step: setup_console_command из install.sh с ROOT_DIR=$INSTALL
install_step() {
  local lib="$ROOT_DIR/scripts/console-command.sh" fn
  fn="$(extract "$ROOT_DIR/install.sh" setup_console_command)"
  ROOT_DIR="$INSTALL" bash -c '
    set -euo pipefail
    log() { echo "LOG $*"; }
    warn() { echo "WARN $*"; }
    install_set_step() { :; }
    source "$1"
    eval "$2"
    setup_console_command
  ' bash "$lib" "$fn" >"$TMP/out" 2>&1
}

echo "[test] install.sh ставит команду во всех режимах (шаг run_install_flow)"
grep -qx '  setup_console_command' <<<"$(extract "$ROOT_DIR/install.sh" run_install_flow)" && ok "шаг в run_install_flow" \
  || bad "setup_console_command не вызывается из run_install_flow"
install_step && ok "код 0" || bad "код $?: $(cat "$TMP/out")"
[[ "$(readlink "$LINK")" == "$INSTALL/scripts/adminpanel-menu.sh" ]] && ok "ссылка" || bad "$(readlink "$LINK" || true)"
grep -q "^LOG Консольное меню: sudo adminpanelaz" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"
rm -f "$LINK"
echo "#!/bin/sh" >"$LINK"
install_step && ok "чужой файл — установка продолжается" || bad "код $?"
grep -q "^WARN .*не ссылка AdminPanelAZ" "$TMP/out" && ok "предупреждение" || bad "вывод: $(cat "$TMP/out")"
rm -f "$LINK"

# uninstall_step: remove_console_command из uninstall.sh с ROOT_DIR=$INSTALL
uninstall_step() {
  local fn
  fn="$(extract "$ROOT_DIR/scripts/uninstall.sh" remove_console_command)"
  ROOT_DIR="$INSTALL" bash -c '
    set -euo pipefail
    log() { echo "LOG $*"; }
    eval "$1"
    remove_console_command
  ' bash "$fn" >"$TMP/out" 2>&1
}

echo "[test] uninstall.sh удаляет ссылку на свой каталог"
grep -qx '  remove_console_command' <<<"$(extract "$ROOT_DIR/scripts/uninstall.sh" main)" && ok "шаг в main" \
  || bad "remove_console_command не вызывается из main"
ln -s "$INSTALL/scripts/adminpanel-menu.sh" "$LINK"
uninstall_step && ok "код 0" || bad "код $?: $(cat "$TMP/out")"
[[ ! -L "$LINK" ]] && grep -q "^LOG Удалена команда $LINK" "$TMP/out" && ok "удалена" || bad "вывод: $(cat "$TMP/out")"
ln -s "$OTHER/scripts/adminpanel-menu.sh" "$LINK"
uninstall_step && ok "код 0" || bad "код $?"
[[ -L "$LINK" ]] && ok "чужая установка — ссылка осталась" || bad "ссылка удалена"
rm -f "$LINK"

# after_pull: panel_after_pull меню из $INSTALL (без pip, интерфейса и unit'ов)
after_pull() {
  set +e
  INSTALL_DIR="$INSTALL" VENV_PATH="$TMP/no-venv" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    panel_after_pull
  ' bash "$INSTALL" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

echo "[test] шаг после обновления ставит команду на уже установленном сервере"
after_pull
[[ "$rc" -eq 0 && "$(readlink "$LINK")" == "$INSTALL/scripts/adminpanel-menu.sh" ]] && ok "ссылка" || bad "код $rc: $(cat "$TMP/out")"
grep -q "Консольное меню: sudo adminpanelaz" "$TMP/out" && ok "сообщение" || bad "вывод: $(cat "$TMP/out")"
rm -f "$LINK"
echo "#!/bin/sh" >"$LINK"
after_pull
[[ "$rc" -eq 0 && ! -L "$LINK" ]] && ok "чужой файл — обновление продолжается" || bad "код $rc"
grep -q "не ссылка AdminPanelAZ" "$TMP/out" && ok "предупреждение" || bad "вывод: $(cat "$TMP/out")"
rm -f "$LINK"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
