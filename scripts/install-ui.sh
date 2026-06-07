#!/usr/bin/env bash
# Общие UI-хелперы для install.sh и install-wizard.sh (не запускать напрямую)
# Рамки и иконки — только ASCII (+ - | [i] [!] …) для совместимости с PuTTY/Windows SSH.

UI_USE_COLOR=false
UI_INTERACTIVE=false
UI_INITIALIZED=false
UI_BOX_WIDTH=62

ui_init() {
  if [[ "$UI_INITIALIZED" == true ]]; then
    return 0
  fi
  UI_INITIALIZED=true
  if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]] && [[ "${TERM:-}" != "dumb" ]]; then
    UI_USE_COLOR=true
  fi
  if [[ -t 0 ]]; then
    UI_INTERACTIVE=true
  fi
}

ui_c() {
  local code="$1"
  shift
  if [[ "$UI_USE_COLOR" == true ]]; then
    printf '\033[%sm%s\033[0m' "$code" "$*"
  else
    printf '%s' "$*"
  fi
}

ui_bold() { ui_c "1" "$*"; }
ui_green() { ui_c "32" "$*"; }
ui_yellow() { ui_c "33" "$*"; }
ui_red() { ui_c "31" "$*"; }
ui_cyan() { ui_c "36" "$*"; }

ui_border_h() {
  printf -- '-%.0s' $(seq 1 "$UI_BOX_WIDTH")
}

ui_detect_version() {
  local pkg="${ROOT_DIR:-}/frontend/package.json"
  if [[ -f "$pkg" ]]; then
    grep -m1 '"version"' "$pkg" 2>/dev/null | sed -E 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/' || true
  fi
}

ui_show_banner() {
  local version
  version="$(ui_detect_version)"
  local ver_line=""
  if [[ -n "$version" ]]; then
    ver_line=" v${version}"
  fi

  echo
  ui_box_top "AdminPanelAZ${ver_line}"
  ui_box_line "Установщик панели управления AntiZapret VPN"
  ui_box_bottom
  echo
}

ui_box_top() {
  local title="$1"
  local border
  border="$(ui_border_h)"
  echo "$(ui_cyan "+${border}+")"
  printf "%s %s\n" "$(ui_cyan "|")" "$(ui_bold "$title")"
  echo "$(ui_cyan "+${border}+")"
}

ui_box_line() {
  local text="$1"
  local plain="$text"
  local pad=$((UI_BOX_WIDTH - ${#plain} - 2))
  if (( pad < 0 )); then
    pad=0
  fi
  printf "%s %s%s %s\n" "$(ui_cyan "|")" "$text" "$(printf '%*s' "$pad" '')" "$(ui_cyan "|")"
}

ui_box_bottom() {
  echo "$(ui_cyan "+$(ui_border_h)+")"
}

ui_separator() {
  local char="${1:--}"
  if [[ "$UI_USE_COLOR" == true ]]; then
    echo "$(ui_cyan "$(printf '%*s' "$UI_BOX_WIDTH" '' | tr ' ' "$char")")"
  else
    printf '%*s\n' "$UI_BOX_WIDTH" '' | tr ' ' "$char"
  fi
}

ui_section() {
  echo
  ui_separator
  ui_bold "$1"
  echo
}

print_info() {
  local msg="$1"
  echo "$(ui_cyan "  [i]")  $msg"
}

print_warn() {
  local msg="$1"
  echo "$(ui_yellow "  [!]")  $msg" >&2
}

print_error() {
  local msg="$1"
  echo "$(ui_red "  [x]")  $msg" >&2
}

print_success() {
  local msg="$1"
  echo "$(ui_green "  [+]")  $msg"
}

ui_info_box() {
  local title="${1:-}"
  shift || true
  local line
  if [[ -n "$title" ]]; then
    echo "  $(ui_cyan "+--") $(ui_bold "$title") $(ui_cyan "$(printf -- '-%.0s' $(seq 1 $((UI_BOX_WIDTH - ${#title} - 6))))+")"
  else
    echo "  +--"
  fi
  for line in "$@"; do
    echo "  $(ui_cyan "|") $line"
  done
  echo "  $(ui_cyan "+$(ui_border_h)+")"
}

ui_warn_box() {
  local title="$1"
  shift
  echo "  $(ui_yellow "+-- [!]") $(ui_bold "$title")"
  local line
  for line in "$@"; do
    echo "  $(ui_yellow "|") $line"
  done
  echo "  $(ui_yellow "+$(ui_border_h)+")"
}

ui_step_header() {
  local current="$1"
  local total="$2"
  local title="$3"
  echo
  ui_separator
  if [[ -n "$total" && "$total" != "?" ]]; then
    ui_bold "Шаг ${current}/${total}: ${title}"
  else
    ui_bold "Шаг ${current}: ${title}"
  fi
  echo
}

ui_summary_row() {
  local label="$1"
  local value="$2"
  local label_pad=24
  if [[ "$UI_USE_COLOR" == true ]]; then
    printf "  $(ui_cyan '%-*s') %s\n" "$label_pad" "${label}:" "$value"
  else
    printf "  %-*s %s\n" "$label_pad" "${label}:" "$value"
  fi
}

ui_summary_title() {
  echo
  ui_box_top "Сводка конфигурации"
  ui_box_bottom
  echo
}

ui_progress_start() {
  local msg="$1"
  UI_PROGRESS_MSG="$msg"
  if [[ "$UI_INTERACTIVE" == true ]]; then
    printf "%s %s...\n" "$(ui_cyan ">")" "$msg"
  else
    printf "[install] %s...\n" "$msg"
  fi
}

ui_progress_done() {
  local msg="${1:-$UI_PROGRESS_MSG}"
  if [[ "$UI_INTERACTIVE" == true && "$UI_USE_COLOR" == true ]]; then
    print_success "${msg} - готово"
  else
    printf "[install] %s - готово\n" "$msg"
  fi
}

ui_show_main_menu() {
  ui_show_banner
  ui_box_top "Выберите действие"
  ui_box_line "  1) Новая установка"
  ui_box_line "     Интерактивный мастер, настройка с нуля"
  ui_box_line "  2) Переустановка"
  ui_box_line "     Резервная копия .env, удаление сервисов, новая установка"
  ui_box_line "  3) Полное удаление"
  ui_box_line "     Остановка сервисов, опционально - каталог проекта"
  ui_box_line "  4) Справка"
  ui_box_line "     Опции CLI и примеры запуска"
  ui_box_bottom
}

ui_confirm() {
  local prompt="$1"
  local default="${2:-n}"
  local danger="${3:-false}"
  local answer=""

  if [[ "$ACCEPT_DEFAULTS" == true ]]; then
    [[ "$default" == "y" ]]
    return $?
  fi

  local hint="y/N"
  if [[ "$default" == "y" ]]; then
    hint="Y/n"
  fi

  if [[ "$danger" == true ]]; then
    echo "$(ui_red "  [!] ОПАСНОЕ ДЕЙСТВИЕ")"
  fi

  read -r -p "$prompt [$hint]: " answer
  answer="${answer:-$default}"
  [[ "$answer" == "y" || "$answer" == "Y" || "$answer" == "yes" || "$answer" == "да" ]]
}

ui_show_help() {
  ui_show_banner
  cat <<'EOF'
Использование: sudo ./install.sh [опции]

Единая точка входа для установки AdminPanelAZ.
Без аргументов (TTY) - интерактивное меню.

Действия:
  (меню)                Новая установка / переустановка / удаление / справка
  --uninstall           Полное удаление сервисов (каталог проекта сохраняется)
  --purge               Вместе с --uninstall: удалить каталог проекта
  --reinstall           Переустановка: удалить сервисы и установить заново

Опции установки:
  --with-daemon         Запустить prod daemon через start.sh после установки
  --with-systemd        Установить systemd unit (без мастера - флаг явный)
  --with-node-agent     Добавить node agent к панели (без мастера - флаг явный)
  --node-only           Только node agent на VPN-сервере (без панели)
  --force               Перезаписать существующий backend/.env из .env.example
  --non-interactive     Без интерактивного мастера (флаги и переменные окружения)
  -y, --yes             Принять значения по умолчанию
  --help, -h            Показать эту справку

Без TTY (pipe, CI):
  wget|curl | sudo bash без флагов НЕ поддерживается — мастер недоступен.
  Скачайте скрипт: wget -qO /tmp/install.sh URL && sudo bash /tmp/install.sh
  Или явные флаги: --non-interactive --with-systemd / --node-only --with-systemd

Переменные окружения:
  INSTALL_FROM_GIT      URL репозитория (по умолчанию — основной репозиторий AdminPanelAZ)
  INSTALL_TARGET        Каталог установки при клонировании (по умолчанию /opt/AdminPanelAZ)
  INSTALL_USER          Пользователь systemd-сервисов (по умолчанию root)

Интерактивный режим:
  Мастер задаёт тип (панель / панель+локальный AZ / node-only),
  сеть, администратора, node agent, systemd/daemon и опции .env.
  AntiZapret устанавливается отдельно в /root/antizapret (см. README).

Примеры:
  wget -qO /tmp/install.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install.sh
  sudo bash /tmp/install.sh
  cd /opt/AdminPanelAZ && sudo ./install.sh
  sudo ./install.sh --non-interactive --with-systemd -y
  sudo ./install.sh --node-only --with-systemd -y
  sudo ./install.sh --uninstall -y
  sudo ./install.sh --uninstall --purge -y
  sudo ./install.sh --reinstall
EOF
}

ui_show_success_screen() {
  local title="$1"
  shift
  echo
  echo "$(ui_green "+$(ui_border_h)+")"
  printf "%s %s %s\n" "$(ui_green "|")" "$(ui_bold "$title")" "$(ui_green "$(printf '%*s|' $((UI_BOX_WIDTH - ${#title} - 1)) '')")"
  echo "$(ui_green "+$(ui_border_h)+")"
  local line
  for line in "$@"; do
    ui_box_line "$line"
  done
  ui_box_bottom
  echo
}
