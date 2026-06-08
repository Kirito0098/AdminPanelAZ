#!/usr/bin/env bash
# Ops console menu — обёртка над start.sh, systemd и существующими scripts.
# Не дублирует install.sh wizard; установка: sudo ./install.sh

set -euo pipefail

export LC_ALL="${LC_ALL:-C.UTF-8}"
export LANG="${LANG:-C.UTF-8}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$ROOT_DIR}"
SERVICE_NAME="${SERVICE_NAME:-adminpanelaz}"
VENV_PATH="${VENV_PATH:-$ROOT_DIR/backend/.venv}"
BACKUP_CLI="$ROOT_DIR/scripts/backup-cli.py"
SITE_DIAGNOSTICS="$ROOT_DIR/scripts/site-diagnostics.sh"
START_SH="$ROOT_DIR/start.sh"

GREEN=$(printf '\033[0;32m')
YELLOW=$(printf '\033[1;33m')
RED=$(printf '\033[0;31m')
CYAN=$(printf '\033[0;36m')
NC=$(printf '\033[0m')

ui_ok() { printf "  ${GREEN}✓${NC}  %s\n" "$*"; }
ui_warn() { printf "  ${YELLOW}!${NC}  %s\n" "$*" >&2; }
ui_fail() { printf "  ${RED}✗${NC}  %s\n" "$*" >&2; }
ui_info() { printf "  ${CYAN}i${NC}  %s\n" "$*"; }
ui_section() { printf "\n${CYAN}── %s ──${NC}\n" "$*"; }

_m_border() {
  printf -- '-%.0s' $(seq 1 58)
}

_m_top() { printf "  +%s+\n" "$(_m_border)"; }
_m_bot() { printf "  +%s+\n" "$(_m_border)"; }
_m_sep() { printf "  |%58s|\n" "" | tr ' ' '-'; }
_m_title() {
  local title="$1"
  printf "  | %s" "$title"
  printf "%*s|\n" $((57 - ${#title})) ""
}
_m_item() {
  local text="$1"
  printf "  | %s" "$text"
  printf "%*s|\n" $((57 - ${#text})) ""
}

press_any_key() {
  if [[ -t 0 ]]; then
    printf "\n"
    read -r -p "  Нажмите Enter…" _ || true
  fi
}

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    ui_fail "Нужны права root (sudo)."
    exit 1
  fi
}

panel_uses_systemd() {
  [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]
}

_menu_python() {
  if [[ -x "$VENV_PATH/bin/python" ]]; then
    printf '%s\n' "$VENV_PATH/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  return 1
}

panel_restart() {
  require_root
  ui_info "Перезапуск панели…"
  if panel_uses_systemd; then
    systemctl restart "$SERVICE_NAME"
    ui_ok "systemctl restart $SERVICE_NAME"
  elif [[ -x "$START_SH" ]]; then
    "$START_SH" restart
    ui_ok "./start.sh restart"
  else
    ui_fail "Не найден systemd unit и $START_SH"
    return 1
  fi
}

panel_status() {
  printf "\n"
  if panel_uses_systemd; then
    systemctl status "$SERVICE_NAME" --no-pager -l || true
  elif [[ -x "$START_SH" ]]; then
    "$START_SH" status || true
  else
    ui_fail "Панель не установлена через systemd и start.sh недоступен"
    return 1
  fi
}

panel_logs() {
  printf "\n"
  if panel_uses_systemd; then
    journalctl -u "$SERVICE_NAME" -n 50 --no-pager || true
  elif [[ -d "${ADMINPANELAZ_STATE_DIR:-$ROOT_DIR/.runtime}/logs" ]]; then
    local log_dir="${ADMINPANELAZ_STATE_DIR:-$ROOT_DIR/.runtime}/logs"
    ui_info "Последние строки из $log_dir:"
    tail -n 50 "$log_dir"/*.log 2>/dev/null || ui_warn "Логи не найдены"
  else
    ui_warn "journalctl недоступен; каталог логов не найден"
  fi
}

panel_update() {
  require_root
  if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    ui_fail "Каталог $INSTALL_DIR не является git-репозиторием"
    return 1
  fi
  if ! command -v git >/dev/null 2>&1; then
    ui_fail "git не найден"
    return 1
  fi

  ui_section "Обновление AdminPanelAZ"
  ui_info "git fetch origin…"
  if ! git -C "$INSTALL_DIR" fetch origin --quiet; then
    ui_fail "git fetch не удался"
    return 1
  fi

  local local_rev remote_rev
  local_rev="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
  remote_rev="$(git -C "$INSTALL_DIR" rev-parse origin/main 2>/dev/null || git -C "$INSTALL_DIR" rev-parse origin/master 2>/dev/null || true)"
  if [[ -z "$remote_rev" ]]; then
    ui_fail "Не найдена ветка origin/main (или origin/master)"
    return 1
  fi

  if [[ "$local_rev" == "$remote_rev" ]]; then
    ui_ok "Репозиторий актуален ($(git -C "$INSTALL_DIR" rev-parse --short HEAD))"
    return 0
  fi

  ui_info "Найдены обновления. git pull --ff-only…"
  if ! git -C "$INSTALL_DIR" pull --ff-only origin main 2>/dev/null && \
     ! git -C "$INSTALL_DIR" pull --ff-only origin master 2>/dev/null; then
    ui_fail "git pull не удался (возможен конфликт — обновите вручную)"
    return 1
  fi
  ui_ok "Код обновлён"

  if [[ -x "$VENV_PATH/bin/pip" && -f "$ROOT_DIR/backend/requirements.txt" ]]; then
    ui_info "Обновление Python-зависимостей…"
    if "$VENV_PATH/bin/pip" install -q -r "$ROOT_DIR/backend/requirements.txt"; then
      ui_ok "Зависимости обновлены"
    else
      ui_warn "pip install завершился с ошибкой — проверьте вручную"
    fi
  fi

  ui_info "Перезапустите панель: $0 --restart"
  return 0
}

panel_backup() {
  require_root
  local py
  py="$(_menu_python)" || {
    ui_fail "Python не найден ($VENV_PATH/bin/python или python3)"
    return 1
  }
  if [[ ! -f "$BACKUP_CLI" ]]; then
    ui_fail "Не найден $BACKUP_CLI"
    return 1
  fi

  ui_section "Резервная копия панели"
  local archive code
  set +e
  archive="$(INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" \
    "$py" "$BACKUP_CLI" create 2>&1)"
  code=$?
  set -e
  if [[ "$code" -eq 0 && -n "$archive" ]]; then
    ui_ok "Архив: $archive"
  else
    ui_fail "Бэкап не создан"
    [[ -n "$archive" ]] && printf '%s\n' "$archive" >&2
    return "$code"
  fi
}

panel_tests() {
  local py pytest_bin
  py="$(_menu_python)" || {
    ui_fail "Python не найден"
    return 1
  }
  if [[ -x "$VENV_PATH/bin/pytest" ]]; then
    pytest_bin="$VENV_PATH/bin/pytest"
  elif command -v pytest >/dev/null 2>&1; then
    pytest_bin="$(command -v pytest)"
  else
    ui_fail "pytest не найден. Установите: $VENV_PATH/bin/pip install -r backend/requirements-dev.txt"
    return 1
  fi
  if [[ ! -d "$ROOT_DIR/backend/tests" ]]; then
    ui_fail "Каталог тестов не найден: $ROOT_DIR/backend/tests"
    return 1
  fi

  ui_section "Автотесты (pytest)"
  ui_info "Модульные тесты для проверки кода; на рабочем сервере запуск не обязателен."
  printf "\n"
  (cd "$ROOT_DIR/backend" && "$pytest_bin" tests/ -q --tb=no)
  local code=$?
  printf "\n"
  if [[ "$code" -eq 0 ]]; then
    ui_ok "Все тесты прошли"
  else
    ui_fail "Есть упавшие тесты (код: $code)"
  fi
  return "$code"
}

panel_diagnose() {
  if [[ ! -f "$SITE_DIAGNOSTICS" ]]; then
    ui_fail "Не найден $SITE_DIAGNOSTICS"
    return 1
  fi
  INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" VENV_PATH="$VENV_PATH" \
    bash "$SITE_DIAGNOSTICS"
}

menu_service_panel() {
  while true; do
    clear || true
    _m_top
    _m_title "Сервис панели"
    _m_sep
    _m_item "1. Перезапустить"
    _m_item "2. Статус"
    _m_item "3. Журнал"
    _m_sep
    _m_item "0. Назад"
    _m_bot
    printf "\n"

    read -r -p "  Выберите действие [0-3]: " choice
    case "$choice" in
      1) panel_restart; press_any_key ;;
      2) panel_status; press_any_key ;;
      3) panel_logs; press_any_key ;;
      0) break ;;
      *)
        ui_warn "Неверный выбор"
        sleep 1
        ;;
    esac
  done
}

menu_backups_updates() {
  while true; do
    clear || true
    _m_top
    _m_title "Резервные копии и обновления"
    _m_sep
    _m_item "1. Проверить обновления (git)"
    _m_item "2. Создать резервную копию"
    _m_sep
    _m_item "0. Назад"
    _m_bot
    printf "\n"

    read -r -p "  Выберите действие [0-2]: " choice
    case "$choice" in
      1) panel_update; press_any_key ;;
      2) panel_backup; press_any_key ;;
      0) break ;;
      *)
        ui_warn "Неверный выбор"
        sleep 1
        ;;
    esac
  done
}

menu_diagnostics_tests() {
  while true; do
    clear || true
    _m_top
    _m_title "Диагностика и тесты"
    _m_sep
    _m_item "1. Диагностика запуска сайта"
    _m_item "2. Автотесты (pytest)"
    _m_sep
    _m_item "0. Назад"
    _m_bot
    printf "\n"

    read -r -p "  Выберите действие [0-2]: " choice
    case "$choice" in
      1) panel_diagnose; press_any_key ;;
      2) panel_tests; press_any_key ;;
      0) break ;;
      *)
        ui_warn "Неверный выбор"
        sleep 1
        ;;
    esac
  done
}

main_menu() {
  while true; do
    clear || true
    _m_top
    _m_title "AdminPanelAZ — Ops console"
    _m_sep
    _m_item "1. Сервис панели"
    _m_item "2. Резервные копии и обновления"
    _m_item "3. Диагностика и тесты"
    _m_sep
    _m_item "7. Диагностика запуска сайта"
    _m_item "8. Автотесты (pytest)"
    _m_sep
    _m_item "0. Выход"
    _m_bot
    printf "\n"
    ui_info "Установка: sudo ./install.sh (не этот скрипт)"

    read -r -p "  Выберите действие [0-8]: " choice
    case "$choice" in
      1) menu_service_panel ;;
      2) menu_backups_updates ;;
      3) menu_diagnostics_tests ;;
      7) panel_diagnose; press_any_key ;;
      8) panel_tests; press_any_key ;;
      0) exit 0 ;;
      *)
        ui_warn "Неверный выбор"
        sleep 1
        ;;
    esac
  done
}

usage() {
  cat <<EOF
Использование: sudo ./scripts/adminpanel-menu.sh [опция]

Интерактивное ops-меню (без мастера install.sh):
  restart, update, backup, pytest, site diagnostics.

Опции (как adminpanel.sh в AA):
  --restart     Перезапустить панель (systemd или start.sh)
  --update      git fetch + pull + pip (если есть обновления)
  --backup      Создать резервную копию (scripts/backup-cli.py)
  --tests       Запустить pytest в backend/tests
  --diagnose    Диагностика запуска (scripts/site-diagnostics.sh)
  --help        Эта справка

Без опций — интерактивное меню.
Установка / переустановка: sudo ./install.sh
EOF
}

main() {
  case "${1:-}" in
    --restart)
      panel_restart
      ;;
    --update)
      panel_update
      ;;
    --backup)
      panel_backup
      ;;
    --tests)
      panel_tests
      exit $?
      ;;
    --diagnose)
      panel_diagnose
      exit $?
      ;;
    --help|-h)
      usage
      ;;
    "")
      if [[ ! -t 0 ]]; then
        usage >&2
        exit 1
      fi
      main_menu
      ;;
    *)
      ui_fail "Неизвестный аргумент: $1"
      usage >&2
      exit 1
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
