#!/usr/bin/env bash
# Полное обновление (sudo ./install.sh --update): код из upstream, затем заново пакеты apt, Python, интерфейс,
# unit'ы systemd, vhost nginx, firewall, DDNS и перезапуск — по текущим настройкам, без мастера.
# База, backend/.env, *_agent.env, сертификаты и mTLS не меняются. Запускает install.sh; подключённый через
# source (тесты) скрипт только объявляет функции.
set -euo pipefail

FU_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
# shellcheck source=scripts/adminpanel-menu.sh
source "$FU_DIR/adminpanel-menu.sh"
# shellcheck source=scripts/python-runtime.sh
source "$FU_DIR/python-runtime.sh"
# shellcheck source=scripts/system-packages.sh
source "$FU_DIR/system-packages.sh"

FU_STEPS=(backup code apt pip frontend systemd nginx firewall ddns restart)
declare -A FU_LABELS=(
  [backup]=Бэкап [code]=Код [apt]=Пакеты [pip]=Python [frontend]=Интерфейс
  [systemd]=systemd [nginx]=nginx [firewall]=firewall [ddns]=DDNS [restart]=Перезапуск
)
# Ошибка этих шагов останавливает обновление до перезапуска: панель продолжает работать на прежнем коде.
FU_STOP_STEPS=" backup code pip frontend "
FU_STATE=""
FU_STOPPED=false
FU_EXIT=0
FU_ARROW="->"
case "${MENU_USER_LOCALE,,}" in
  *utf-8* | *utf8*) FU_ARROW="→" ;;
esac

# Итог — в файле, а не в переменных: шаги идут в подоболочках, а после обновления кода продолжает новый процесс.
fu_row() {
  local detail="${3:-}"
  detail="${detail//[$'\t\n']/ }"
  printf '%s\t%s\t%s\n' "$1" "$2" "$detail" >>"$FU_STATE"
}

fu_field() {
  awk -F'\t' -v key="$1" -v n="$2" '$1 == key { value = $n } END { print value }' "$FU_STATE"
}

fu_fail_detail() {
  case "$1" in
    backup) echo "бэкап не создан — обновление не начиналось" ;;
    code) echo "код не обновлён — подробности выше" ;;
    pip) echo "pip install не прошёл — панель не перезапускалась" ;;
    frontend) echo "сборка не прошла — панель не перезапускалась; вручную: cd $INSTALL_DIR/frontend && npm ci && npm run build:all" ;;
    systemd) echo "refresh-systemd-units.sh завершился с ошибкой — проверьте unit'ы вручную" ;;
    *) echo "непредвиденная ошибка (код $2), см. вывод выше" ;;
  esac
}

# Шаг — в подоболочке с set -e: отказ команды завершает шаг, а не всё обновление. Вызывать только отдельной
# командой: в `fu_run … || …` и `if fu_run …` bash отключает set -e и внутри подоболочки.
fu_run() {
  local key="$1" rc
  if [[ "$FU_STOPPED" == true ]]; then
    return 0
  fi
  ui_section "${FU_LABELS[$key]}"
  set +e
  (set -e; "$2")
  rc=$?
  set -e
  if [[ -z "$(fu_field "$key" 2)" ]]; then
    if [[ "$rc" -eq 0 ]]; then
      fu_row "$key" ok
    else
      fu_row "$key" ошибка "$(fu_fail_detail "$key" "$rc")"
    fi
  fi
  if [[ "$rc" -ne 0 && "$FU_STOP_STEPS" == *" $key "* ]]; then
    FU_STOPPED=true
  fi
  return 0
}

# printf %-10s в bash считает байты, а буква кириллицы — два байта.
fu_pad() {
  local text="$1" width="$2"
  printf '%s' "$text"
  if ((${#text} < width)); then
    printf '%*s' "$((width - ${#text}))" ''
  fi
}

fu_status_color() {
  case "$1" in
    ok) printf '%s' "$C_OK" ;;
    ошибка) printf '%s' "$C_ERR" ;;
    *) printf '%s' "$C_DIM" ;;
  esac
}

fu_summary() {
  local key status detail width
  width="$(($(menu_cols) - 23))"
  ui_section "Полное обновление"
  for key in "${FU_STEPS[@]}"; do
    status="$(fu_field "$key" 2)"
    detail="$(fu_field "$key" 3)"
    if [[ -z "$status" ]]; then
      status=пропущен
      detail="не выполнялся"
    fi
    printf '  %s %s' "$(fu_pad "${FU_LABELS[$key]}" 10)" "$(fu_status_color "$status")"
    if [[ -n "$detail" ]]; then
      printf '%s%s  %s\n' "$(fu_pad "$status" 8)" "$C_RESET" "$(menu_fit "$detail" "$width")"
    else
      printf '%s%s\n' "$status" "$C_RESET"
    fi
  done
}

fu_finish() {
  local backup
  fu_summary
  FU_EXIT=0
  if awk -F'\t' '$2 == "ошибка" { found = 1 } END { exit !found }' "$FU_STATE"; then
    # shellcheck disable=SC2034
    FU_EXIT=1
  fi
  if [[ "$(fu_field restart 3)" == *"панель не ответила"* ]]; then
    backup="$(fu_field backup 3)"
    printf '\n'
    ui_warn "Панель не ответила после обновления. Бэкап до обновления: ${backup:-нет}"
    ui_info "Восстановить: sudo adminpanelaz $FU_ARROW 6 Бэкап и восстановление"
  fi
  rm -f "$FU_STATE"
}

fu_head() {
  git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null || true
}

fu_step_backup() {
  if ! panel_uses_systemd; then
    fu_row backup пропущен "нет панели"
    return 0
  fi
  panel_backup --no-prune --keep-running
  fu_row backup ok "${PANEL_LAST_BACKUP##*/}"
}

# Код — функцией меню: fast-forward из upstream текущей ветки, reset после force-push только при чистом дереве.
fu_step_code() {
  local before after
  before="$(fu_head)"
  PANEL_UPDATE_CODE_ONLY=true
  panel_update
  after="$(fu_head)"
  if [[ "$before" == "$after" ]]; then
    fu_row code ok "актуально, $after"
  else
    fu_row code ok "$before $FU_ARROW $after"
  fi
}

# Остальные шаги — уже обновлённым установщиком: новые шаблоны и новый код шагов. Исходная локаль — для значков.
full_update_reexec() {
  ui_info "Код обновлён — дальше работает обновлённый install.sh"
  exec env LC_ALL="$MENU_USER_LC_ALL" LANG="$MENU_USER_LANG" \
    "${BASH:-bash}" "$INSTALL_DIR/install.sh" --update -y --update-resume="$FU_STATE"
}

fu_apt_packages() {
  local mm
  printf '%s\n' "${ADMINPANELAZ_APT_PACKAGES[@]}"
  mm="$(ap_python_mm "$(ap_venv_report_version "$VENV_PATH" || true)" || true)"
  if [[ -n "$mm" ]]; then
    ap_python_apt_packages_for "$mm" | tr ' ' '\n'
  fi
}

fu_pkg_installed() {
  local status
  status="$(dpkg -s "$1" 2>/dev/null)" || return 1
  grep -qx 'Status: install ok installed' <<<"$status"
}

# Уже установленные пакеты не обновляются (--no-upgrade); ошибка apt не останавливает обновление.
fu_step_apt() {
  local pkg
  local -a missing=()
  while IFS= read -r pkg; do
    if [[ -n "$pkg" ]] && ! fu_pkg_installed "$pkg"; then
      missing+=("$pkg")
    fi
  done < <(fu_apt_packages)
  if [[ "${#missing[@]}" -eq 0 ]]; then
    ui_ok "Все пакеты apt на месте"
    fu_row apt ok "доустановлено: 0"
    return 0
  fi
  ui_info "Доустановка: ${missing[*]}"
  if DEBIAN_FRONTEND=noninteractive apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-upgrade "${missing[@]}"; then
    fu_row apt ok "доустановлено: ${#missing[@]} (${missing[*]})"
    return 0
  fi
  ui_warn "apt-get не доустановил пакеты — обновление продолжается"
  fu_row apt ошибка "не доустановлено: ${missing[*]}"
}

fu_step_pip() {
  local pip="$VENV_PATH/bin/pip"
  if [[ ! -x "$pip" ]]; then
    ui_fail "Нет $pip — виртуальное окружение Python не найдено"
    fu_row pip ошибка "нет $pip"
    return 1
  fi
  ui_info "pip install -r backend/requirements.txt…"
  "$pip" install -q -r "$INSTALL_DIR/backend/requirements.txt"
  ui_ok "Python-зависимости обновлены"
  fu_row pip ok
}

fu_step_frontend() {
  if ! panel_uses_systemd; then
    fu_row frontend пропущен "нет панели"
    return 0
  fi
  panel_build_frontend
  fu_row frontend ok
}

fu_refresh_units() {
  SYSTEMD_UNIT_DIR="$UNIT_DIR" bash "$INSTALL_DIR/scripts/refresh-systemd-units.sh"
}

fu_units_list() {
  local list="" unit
  if panel_uses_systemd; then
    list="$SERVICE_NAME"
  fi
  while IFS= read -r unit; do
    list+="${list:+, }$unit"
  done < <(menu_agent_units)
  printf '%s' "$list"
}

fu_step_systemd() {
  fu_refresh_units
  ui_ok "Unit'ы обновлены из шаблонов: $(fu_units_list)"
  fu_row systemd ok "$(fu_units_list)"
}
