#!/usr/bin/env bash
# Команда adminpanelaz — symlink на консольное меню. Подключают install.sh, uninstall.sh и adminpanel-menu.sh.

console_command_path() {
  printf '%s\n' "${ADMINPANELAZ_MENU_LINK:-/usr/local/bin/adminpanelaz}"
}

# console_command_link <каталог установки>: 0 — ссылка на меню этого каталога стоит;
# 2 — на этом месте файл, который не ссылка (не перезаписываем); иначе — ошибка mkdir/ln.
console_command_link() {
  local link
  link="$(console_command_path)"
  if [[ -e "$link" && ! -L "$link" ]]; then
    return 2
  fi
  mkdir -p "$(dirname "$link")" && ln -sfn "$1/scripts/adminpanel-menu.sh" "$link"
}

# console_command_unlink <каталог установки>: 0 — ссылка вела в этот каталог и удалена; 1 — удалять нечего.
console_command_unlink() {
  local link
  link="$(console_command_path)"
  [[ -L "$link" ]] || return 1
  [[ "$(readlink -m "$link")" == "$(readlink -m "$1")"/* ]] || return 1
  rm -f "$link"
}
