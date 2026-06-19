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
  ui_box_top "Главное меню — что вы хотите сделать?"
  ui_box_line "  1) Новая установка  (рекомендуется)"
  ui_box_line "     Пошаговый мастер: настроит панель с нуля"
  ui_box_line "  2) Переустановка"
  ui_box_line "     Сохранит .env, удалит сервисы и поставит заново"
  ui_box_line "  3) Удаление"
  ui_box_line "     Остановит сервисы; каталог проекта останется"
  ui_box_line "  4) Удалить всё без следов"
  ui_box_line "     Снесёт сервисы, конфиг, БД, проект и бэкапы"
  ui_box_line "  5) Справка"
  ui_box_line "     Список опций командной строки и примеры"
  ui_box_bottom
  echo
  print_info "Введите номер и нажмите Enter. По умолчанию — 1 (новая установка)."
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
AdminPanelAZ — веб-панель управления AntiZapret VPN.
Этот скрипт ставит, обновляет и удаляет панель и/или агент узла.

Использование:
  sudo ./install.sh [опции]

================================================================
  БЫСТРЫЙ СТАРТ
================================================================
  Проще всего — запустить без опций, откроется меню с подсказками:
      sudo ./install.sh

  Новичкам рекомендуем простой мастер с пояснениями на каждом шаге:
      sudo ./install-easy.sh

================================================================
  1. ЧТО СДЕЛАТЬ (действие)
================================================================
  (без опций)         Открыть интерактивное меню (установка / удаление / справка)
  --easy              Простой пошаговый мастер для новичков (= install-easy.sh)
  --reinstall         Переустановить: сохранить .env, снести сервисы, поставить заново
  --uninstall         Удалить сервисы и конфигурацию (каталог проекта остаётся)
  --uninstall --purge Удалить сервисы + сам каталог проекта
  --purge-all         Удалить ВСЁ без следов (сервисы, проект, БД, бэкапы)

================================================================
  2. ЧТО УСТАНОВИТЬ (роль сервера)
================================================================
  (по умолчанию)      Панель управления — веб-интерфейс и API (controller)
  --with-node-agent   Панель + локальный агент узла на этом же сервере
  --node-only         Только агент узла для VPN-сервера (без панели)

================================================================
  3. КАК ЗАПУСКАТЬ ПОСЛЕ УСТАНОВКИ (автозапуск)
================================================================
  --with-systemd      Системный сервис, автозапуск при загрузке (рекомендуется)
  --with-daemon       Фоновый процесс через start.sh (без systemd)
  (ничего)            Не запускать — в конце покажем команды для ручного старта

================================================================
  4. ПРОЧИЕ ОПЦИИ
================================================================
  --force             Перезаписать существующий backend/.env из шаблона .env.example
  --non-interactive   Тихий режим без мастера (настройка только флагами и WIZ_*)
  -y, --yes           Соглашаться со значениями по умолчанию (не задавать вопросов)
  --help, -h          Показать эту справку

================================================================
  ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
================================================================
  INSTALL_FROM_GIT    URL репозитория (по умолчанию — основной репозиторий AdminPanelAZ)
  INSTALL_TARGET      Каталог установки при клонировании (по умолчанию /opt/AdminPanelAZ)
  INSTALL_USER        Пользователь systemd-сервисов (по умолчанию root)

================================================================
  УСТАНОВКА БЕЗ ТЕРМИНАЛА (CI / автоматизация)
================================================================
  Запуск «wget|curl | sudo bash» без флагов НЕ поддерживается:
  без терминала мастер недоступен и тип установки определить нельзя.

  Сначала скачайте скрипт, затем запустите:
      wget -qO /tmp/install.sh <URL> && sudo bash /tmp/install.sh

  Либо передайте явные флаги (минимальная установка панели):
      sudo ./install.sh --non-interactive --with-systemd -y

  Для production задайте настройки через переменные WIZ_* перед запуском:
      WIZ_APP_ENV=production WIZ_NGINX_MODE=le WIZ_NGINX_DOMAIN=panel.example.com \
      WIZ_NGINX_EMAIL=admin@example.com WIZ_CONFIGURE_FIREWALL=true \
      WIZ_ADMIN_USERNAME=admin WIZ_ADMIN_PASSWORD=... WIZ_BACKEND_PORT=8000 \
      WIZ_INSTALL_TYPE=controller \
        sudo -E ./install.sh --non-interactive --with-systemd -y

================================================================
  ПРИМЕРЫ
================================================================
  # Новичкам — простой мастер
  sudo ./install-easy.sh

  # Обычная установка с меню (из каталога проекта)
  cd /opt/AdminPanelAZ && sudo ./install.sh

  # Скачать и запустить мастер
  wget -qO /tmp/install.sh https://raw.githubusercontent.com/Kirito0098/AdminPanelAZ/refs/heads/main/install.sh
  sudo bash /tmp/install.sh

  # Тихая установка панели как systemd-сервиса
  sudo ./install.sh --non-interactive --with-systemd -y

  # Тихая установка только агента узла на VPN-сервере
  sudo ./install.sh --node-only --with-systemd -y

  # Удаление / переустановка
  sudo ./install.sh --uninstall -y           # удалить сервисы
  sudo ./install.sh --uninstall --purge -y   # + удалить каталог проекта
  sudo ./install.sh --reinstall              # переустановить с сохранением .env

Примечание: AntiZapret устанавливается отдельно в /root/antizapret (см. README).
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
