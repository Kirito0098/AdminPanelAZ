#!/usr/bin/env bash
# Интерактивный мастер установки AdminPanelAZ (подключается из install.sh)
set -euo pipefail

# shellcheck disable=SC2034
WIZ_INSTALL_TYPE="${WIZ_INSTALL_TYPE:-controller}"
WIZ_ANTIZAPRET_PATH="${WIZ_ANTIZAPRET_PATH:-/root/antizapret}"
WIZ_BACKEND_HOST="${WIZ_BACKEND_HOST:-0.0.0.0}"
WIZ_BACKEND_PORT="${WIZ_BACKEND_PORT:-8000}"
WIZ_SERVER_ADDRESS="${WIZ_SERVER_ADDRESS:-}"
WIZ_CORS_ORIGINS="${WIZ_CORS_ORIGINS:-}"
WIZ_ALLOW_INTERNAL_NODES="${WIZ_ALLOW_INTERNAL_NODES:-false}"
WIZ_ADMIN_USERNAME="${WIZ_ADMIN_USERNAME:-admin}"
WIZ_ADMIN_PASSWORD="${WIZ_ADMIN_PASSWORD:-admin}"
WIZ_ADMIN_MUST_CHANGE_PASSWORD="${WIZ_ADMIN_MUST_CHANGE_PASSWORD:-true}"
WIZ_NODE_AGENT_PORT="${WIZ_NODE_AGENT_PORT:-9100}"
WIZ_NODE_AGENT_API_KEY="${WIZ_NODE_AGENT_API_KEY:-}"
WIZ_RUN_MODE="${WIZ_RUN_MODE:-manual}"
WIZ_CIDR_DB_REFRESH_ENABLED="${WIZ_CIDR_DB_REFRESH_ENABLED:-true}"
WIZ_CIDR_DB_REFRESH_HOUR="${WIZ_CIDR_DB_REFRESH_HOUR:-2}"
WIZ_CIDR_DB_REFRESH_MINUTE="${WIZ_CIDR_DB_REFRESH_MINUTE:-30}"
WIZ_TRAFFIC_SYNC_ENABLED="${WIZ_TRAFFIC_SYNC_ENABLED:-true}"
WIZ_TELEGRAM_ENABLED="${WIZ_TELEGRAM_ENABLED:-false}"
WIZ_TELEGRAM_BOT_TOKEN="${WIZ_TELEGRAM_BOT_TOKEN:-}"
WIZ_TELEGRAM_CHAT_ID="${WIZ_TELEGRAM_CHAT_ID:-}"
WIZ_AUTO_BACKUP_ENABLED="${WIZ_AUTO_BACKUP_ENABLED:-false}"
WIZ_AUTO_BACKUP_DAYS="${WIZ_AUTO_BACKUP_DAYS:-7}"
WIZ_STATE_DIR="${WIZ_STATE_DIR:-}"
WIZ_NODE_STATE_DIR="${WIZ_NODE_STATE_DIR:-}"
WIZ_BACKUP_ROOT="${WIZ_BACKUP_ROOT:-/var/backups/adminpanelaz}"

WIZ_ACCEPT_DEFAULTS="${WIZ_ACCEPT_DEFAULTS:-false}"
WIZ_APPLY_CONFIRMED="${WIZ_APPLY_CONFIRMED:-false}"

_wiz_use_color=false
if [[ -t 1 ]] && [[ "${TERM:-}" != "dumb" ]]; then
  _wiz_use_color=true
fi

_wiz_c() {
  local code="$1"
  shift
  if [[ "$_wiz_use_color" == true ]]; then
    printf '\033[%sm%s\033[0m' "$code" "$*"
  else
    printf '%s' "$*"
  fi
}

wiz_title() {
  echo
  _wiz_c "1;36" "=== $* ==="
  echo
}

wiz_step() {
  _wiz_c "1;33" "$*"
}

wiz_prompt() {
  local prompt="$1"
  local default="${2:-}"
  local reply=""

  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    if [[ -n "$default" ]]; then
      REPLY="$default"
    else
      REPLY=""
    fi
    echo "$prompt [$default]"
    return 0
  fi

  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " reply
    REPLY="${reply:-$default}"
  else
    read -r -p "$prompt: " reply
    REPLY="$reply"
  fi
}

wiz_prompt_secret() {
  local prompt="$1"
  local default="${2:-}"
  local reply=""
  local reply2=""

  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    REPLY="$default"
    echo "$prompt [***]"
    return 0
  fi

  while true; do
    read -r -s -p "$prompt: " reply
    echo
    if [[ -z "$reply" && -n "$default" ]]; then
      REPLY="$default"
      return 0
    fi
    read -r -s -p "Подтвердите пароль: " reply2
    echo
    if [[ "$reply" == "$reply2" ]]; then
      REPLY="$reply"
      return 0
    fi
    echo "Пароли не совпадают, повторите."
  done
}

wiz_prompt_yesno() {
  local prompt="$1"
  local default="${2:-n}"
  local reply=""

  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    REPLY="$default"
    echo "$prompt [${default}]"
    return 0
  fi

  local hint="y/N"
  if [[ "$default" == "y" ]]; then
    hint="Y/n"
  fi

  read -r -p "$prompt [$hint]: " reply
  reply="${reply:-$default}"
  case "$reply" in
    y|Y|yes|Yes|да|Да)
      REPLY="y"
      ;;
    *)
      REPLY="n"
      ;;
  esac
}

wiz_prompt_port() {
  local prompt="$1"
  local default="$2"

  while true; do
    wiz_prompt "$prompt" "$default"
    if [[ "$REPLY" =~ ^[0-9]+$ ]] && (( REPLY >= 1 && REPLY <= 65535 )); then
      return 0
    fi
    echo "Введите число от 1 до 65535."
  done
}

wiz_prompt_choice() {
  local prompt="$1"
  shift
  local options=("$@")
  local i choice

  echo "$prompt"
  for i in "${!options[@]}"; do
    echo "  $((i + 1))) ${options[$i]}"
  done

  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    REPLY="1"
    echo "Выбор [1]: ${options[0]}"
    return 0
  fi

  while true; do
    read -r -p "Выберите [1-${#options[@]}]: " choice
    choice="${choice:-1}"
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
      REPLY="$choice"
      return 0
    fi
    echo "Неверный выбор."
  done
}

wizard_derive_cors_origins() {
  local port="$1"
  local origins="http://127.0.0.1:${port},http://localhost:${port},http://127.0.0.1:5173,http://localhost:5173"

  if [[ -n "$WIZ_SERVER_ADDRESS" ]]; then
    local addr="$WIZ_SERVER_ADDRESS"
    addr="${addr#http://}"
    addr="${addr#https://}"
    addr="${addr%%/*}"
    origins="${origins},http://${addr}:${port},https://${addr}:${port}"
  fi

  WIZ_CORS_ORIGINS="$origins"
}

wizard_check_antizapret() {
  if [[ -d "$WIZ_ANTIZAPRET_PATH" && -f "$WIZ_ANTIZAPRET_PATH/client.sh" ]]; then
    echo "  AntiZapret найден: $WIZ_ANTIZAPRET_PATH"
    return 0
  fi

  echo "  ВНИМАНИЕ: AntiZapret не найден в $WIZ_ANTIZAPRET_PATH"
  wiz_prompt_yesno "  Продолжить установку без AntiZapret?" "n"
  if [[ "$REPLY" != "y" ]]; then
    die "Установка прервана. Укажите корректный путь к AntiZapret."
  fi
}

wizard_ask_install_type() {
  wiz_step "1. Тип установки"
  wiz_prompt_choice "Какой компонент устанавливаем?" \
    "Только controller (панель администрирования)" \
    "Controller + Node agent (на одной машине)" \
    "Только Node agent (удалённый VPN-сервер)"

  case "$REPLY" in
    1) WIZ_INSTALL_TYPE="controller" ;;
    2) WIZ_INSTALL_TYPE="controller_node" ;;
    3) WIZ_INSTALL_TYPE="node" ;;
  esac
  echo
}

wizard_ask_antizapret() {
  wiz_step "2. AntiZapret"
  wiz_prompt "Путь к каталогу AntiZapret" "$WIZ_ANTIZAPRET_PATH"
  WIZ_ANTIZAPRET_PATH="$REPLY"
  wizard_check_antizapret
  echo
}

wizard_ask_network() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  wiz_step "3. Сеть и доступ"
  wiz_prompt "Хост backend (0.0.0.0 — все интерфейсы)" "$WIZ_BACKEND_HOST"
  WIZ_BACKEND_HOST="$REPLY"
  wiz_prompt_port "Порт backend" "$WIZ_BACKEND_PORT"
  WIZ_BACKEND_PORT="$REPLY"
  wiz_prompt "IP или домен сервера (для CORS, необязательно)" "$WIZ_SERVER_ADDRESS"
  WIZ_SERVER_ADDRESS="$REPLY"
  wizard_derive_cors_origins "$WIZ_BACKEND_PORT"

  wiz_prompt_yesno "Разрешить внутренние IP для удалённых узлов (ALLOW_INTERNAL_NODES)?" "n"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_ALLOW_INTERNAL_NODES="true"
  else
    WIZ_ALLOW_INTERNAL_NODES="false"
  fi
  echo
}

wizard_ask_admin() {
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    return 0
  fi

  wiz_step "4. Администратор"
  wiz_prompt "Имя администратора по умолчанию" "$WIZ_ADMIN_USERNAME"
  WIZ_ADMIN_USERNAME="$REPLY"

  echo "Пароль администратора (Enter — сгенерировать случайный):"
  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    WIZ_ADMIN_PASSWORD="${WIZ_ADMIN_PASSWORD:-admin}"
    echo "  [используется значение по умолчанию]"
  else
    read -r -s -p "Пароль (пусто = случайный): " _admin_pw
    echo
    if [[ -z "$_admin_pw" ]]; then
      WIZ_ADMIN_PASSWORD="$(random_hex | cut -c1-16)"
      echo "  Сгенерирован пароль: $WIZ_ADMIN_PASSWORD"
    else
      read -r -s -p "Подтвердите пароль: " _admin_pw2
      echo
      if [[ "$_admin_pw" != "$_admin_pw2" ]]; then
        die "Пароли не совпадают."
      fi
      WIZ_ADMIN_PASSWORD="$_admin_pw"
    fi
  fi

  wiz_prompt_yesno "Требовать смену пароля при первом входе?" "y"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_ADMIN_MUST_CHANGE_PASSWORD="true"
  else
    WIZ_ADMIN_MUST_CHANGE_PASSWORD="false"
  fi
  echo
}

wizard_ask_node_agent() {
  if [[ "$WIZ_INSTALL_TYPE" == "controller" ]]; then
    return 0
  fi

  wiz_step "5. Node agent"
  wiz_prompt_port "Порт node agent" "$WIZ_NODE_AGENT_PORT"
  WIZ_NODE_AGENT_PORT="$REPLY"

  wiz_prompt_yesno "Сгенерировать NODE_AGENT_API_KEY автоматически?" "y"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_NODE_AGENT_API_KEY="$(random_hex)"
    echo "  Будет сгенерирован ключ (покажем в конце установки)."
  else
    wiz_prompt_secret "Введите NODE_AGENT_API_KEY" ""
    if [[ -z "$REPLY" ]]; then
      die "NODE_AGENT_API_KEY обязателен для node agent."
    fi
    WIZ_NODE_AGENT_API_KEY="$REPLY"
  fi
  echo
}

wizard_ask_services() {
  wiz_step "6. Сервисы и автозапуск"
  wiz_prompt_choice "Как запускать после установки?" \
    "Вручную (./start.sh / ./start_node_agent.sh)" \
    "Daemon через start.sh (watchdog)" \
    "Systemd (рекомендуется для production)"

  case "$REPLY" in
    1) WIZ_RUN_MODE="manual" ;;
    2) WIZ_RUN_MODE="daemon" ;;
    3) WIZ_RUN_MODE="systemd" ;;
  esac
  echo
}

wizard_ask_optional() {
  local step_num="7"
  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    step_num="3"
  elif [[ "$WIZ_INSTALL_TYPE" == "controller" ]]; then
    step_num="5"
  fi

  wiz_step "${step_num}. Опциональные функции"

  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    wiz_prompt_yesno "Включить ночное обновление CIDR DB (CIDR_DB_REFRESH_ENABLED)?" "y"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_CIDR_DB_REFRESH_ENABLED="true"
      wiz_prompt "Час запуска (0-23)" "$WIZ_CIDR_DB_REFRESH_HOUR"
      WIZ_CIDR_DB_REFRESH_HOUR="$REPLY"
      wiz_prompt "Минута запуска (0-59)" "$WIZ_CIDR_DB_REFRESH_MINUTE"
      WIZ_CIDR_DB_REFRESH_MINUTE="$REPLY"
    else
      WIZ_CIDR_DB_REFRESH_ENABLED="false"
    fi

    wiz_prompt_yesno "Включить сбор трафика (TRAFFIC_SYNC_ENABLED)?" "y"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_TRAFFIC_SYNC_ENABLED="true"
    else
      WIZ_TRAFFIC_SYNC_ENABLED="false"
    fi

    wiz_prompt_yesno "Настроить Telegram-уведомления?" "n"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_TELEGRAM_ENABLED="true"
      wiz_prompt "Telegram Bot Token" ""
      WIZ_TELEGRAM_BOT_TOKEN="$REPLY"
      wiz_prompt "Telegram Chat ID" ""
      WIZ_TELEGRAM_CHAT_ID="$REPLY"
    fi

    wiz_prompt_yesno "Включить автоматические бэкапы?" "n"
    if [[ "$REPLY" == "y" ]]; then
      WIZ_AUTO_BACKUP_ENABLED="true"
      wiz_prompt "Интервал автобэкапа (дней)" "$WIZ_AUTO_BACKUP_DAYS"
      WIZ_AUTO_BACKUP_DAYS="$REPLY"
    fi
  fi
  echo
}

wizard_ask_paths() {
  local step_num="8"
  local default_state="$ROOT_DIR/.runtime"
  local default_node_state="$ROOT_DIR/.runtime/node"

  if [[ "$WIZ_RUN_MODE" == "systemd" ]]; then
    default_state="/var/lib/adminpanelaz"
    default_node_state="/var/lib/adminpanelaz-node"
  fi

  if [[ "$WIZ_INSTALL_TYPE" == "node" ]]; then
    step_num="4"
  elif [[ "$WIZ_INSTALL_TYPE" == "controller" ]]; then
    step_num="6"
  fi

  wiz_step "${step_num}. Пути"
  wiz_prompt "Каталог состояния controller" "${WIZ_STATE_DIR:-$default_state}"
  WIZ_STATE_DIR="$REPLY"

  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    wiz_prompt "Каталог состояния node agent" "${WIZ_NODE_STATE_DIR:-$default_node_state}"
    WIZ_NODE_STATE_DIR="$REPLY"
  fi

  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    wiz_prompt "Каталог бэкапов (BACKUP_ROOT)" "$WIZ_BACKUP_ROOT"
    WIZ_BACKUP_ROOT="$REPLY"
  fi
  echo
}

wizard_apply_run_mode_flags() {
  WITH_DAEMON=false
  WITH_SYSTEMD=false
  WITH_NODE_AGENT=false

  case "$WIZ_RUN_MODE" in
    daemon) WITH_DAEMON=true ;;
    systemd) WITH_SYSTEMD=true ;;
  esac

  case "$WIZ_INSTALL_TYPE" in
    controller_node|node) WITH_NODE_AGENT=true ;;
  esac

  export ADMINPANELAZ_STATE_DIR="$WIZ_STATE_DIR"
  export NODE_AGENT_STATE_DIR="$WIZ_NODE_STATE_DIR"
  export BACKEND_HOST="$WIZ_BACKEND_HOST"
  export BACKEND_PORT="$WIZ_BACKEND_PORT"
  export ANTIZAPRET_PATH="$WIZ_ANTIZAPRET_PATH"
  export NODE_AGENT_PORT="$WIZ_NODE_AGENT_PORT"
  export NODE_AGENT_API_KEY="$WIZ_NODE_AGENT_API_KEY"
}

wizard_show_summary() {
  wizard_apply_run_mode_flags

  wiz_title "Сводка конфигурации"

  echo "  Тип установки:     $WIZ_INSTALL_TYPE"
  echo "  AntiZapret:        $WIZ_ANTIZAPRET_PATH"
  if [[ "$WIZ_INSTALL_TYPE" != "node" ]]; then
    echo "  Backend:           ${WIZ_BACKEND_HOST}:${WIZ_BACKEND_PORT}"
    echo "  CORS:              $WIZ_CORS_ORIGINS"
    echo "  Internal nodes:    $WIZ_ALLOW_INTERNAL_NODES"
    echo "  Администратор:     $WIZ_ADMIN_USERNAME"
    echo "  Смена пароля:      $WIZ_ADMIN_MUST_CHANGE_PASSWORD"
    echo "  BACKUP_ROOT:       $WIZ_BACKUP_ROOT"
    echo "  CIDR refresh:      $WIZ_CIDR_DB_REFRESH_ENABLED"
    echo "  Traffic sync:      $WIZ_TRAFFIC_SYNC_ENABLED"
    echo "  Telegram:          $WIZ_TELEGRAM_ENABLED"
    echo "  Auto-backup:       $WIZ_AUTO_BACKUP_ENABLED"
  fi
  if [[ "$WIZ_INSTALL_TYPE" != "controller" ]]; then
    echo "  Node agent port:   $WIZ_NODE_AGENT_PORT"
    echo "  Node API key:      ${WIZ_NODE_AGENT_API_KEY:0:8}..."
    echo "  Node state dir:    $WIZ_NODE_STATE_DIR"
  fi
  echo "  State dir:         $WIZ_STATE_DIR"
  echo "  Режим запуска:     $WIZ_RUN_MODE"
  echo
}

wizard_confirm_apply() {
  if [[ "$WIZ_ACCEPT_DEFAULTS" == true ]]; then
    WIZ_APPLY_CONFIRMED=true
    return 0
  fi

  wiz_prompt_yesno "Применить конфигурацию?" "n"
  if [[ "$REPLY" == "y" ]]; then
    WIZ_APPLY_CONFIRMED=true
  else
    WIZ_APPLY_CONFIRMED=false
    echo "Установка отменена."
    exit 0
  fi
}

run_install_wizard() {
  wiz_title "AdminPanelAZ — мастер установки"
  echo "Ответьте на вопросы ниже. Enter — значение по умолчанию в [скобках]."
  echo

  wizard_ask_install_type
  wizard_ask_antizapret
  wizard_ask_network
  wizard_ask_admin
  wizard_ask_node_agent
  wizard_ask_services
  wizard_ask_optional
  wizard_ask_paths
  wizard_show_summary
  wizard_confirm_apply
  wizard_apply_run_mode_flags
}

wizard_install_controller() {
  case "$WIZ_INSTALL_TYPE" in
    controller|controller_node) return 0 ;;
    *) return 1 ;;
  esac
}

wizard_install_node() {
  case "$WIZ_INSTALL_TYPE" in
    controller_node|node) return 0 ;;
    *) return 1 ;;
  esac
}
