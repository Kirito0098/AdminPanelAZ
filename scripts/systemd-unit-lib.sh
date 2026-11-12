#!/usr/bin/env bash
# Общий рендер systemd unit из шаблона репо: корень установки, каталог состояния, пользователь и группа.
# Подключается install-systemd.sh, install-node-systemd.sh и install-proxy-systemd.sh — шаблон,
# каталог состояния и порт у каждой службы свои.

# systemd_unit_render <шаблон> <заглушка state-dir в шаблоне> <state-dir> [sed-выражение…]
# UNIT_ROOT, INSTALL_USER и INSTALL_GROUP задаёт скрипт-установщик.
systemd_unit_render() {
  local template="$1" state_placeholder="$2" state_dir="$3"
  shift 3
  local -a sed_args=(
    -e "s|/opt/AdminPanelAZ|${UNIT_ROOT}|g"
    -e "s|${state_placeholder}|${state_dir}|g"
    -e "s|^User=root|User=${INSTALL_USER}|"
    -e "s|^Group=root|Group=${INSTALL_GROUP}|"
  )
  local expr
  for expr in "$@"; do
    sed_args+=(-e "$expr")
  done
  sed "${sed_args[@]}" "$template"
}
