#!/usr/bin/env bash
# Установка AdminPanelAZ на Ubuntu 24.04 / Debian 13+
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/install-ui.sh
source "$ROOT_DIR/scripts/install-ui.sh"
ui_init
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"
NODE_ENV_FILE="$BACKEND_DIR/node_agent.env"
NODE_ENV_EXAMPLE="$BACKEND_DIR/node_agent.env.example"

WITH_DAEMON=false
WITH_SYSTEMD=false
WITH_NODE_AGENT=false
FORCE=false
NON_INTERACTIVE=false
ACCEPT_DEFAULTS=false
INSTALL_FROM_GIT="${INSTALL_FROM_GIT:-}"
INSTALL_TARGET="${INSTALL_TARGET:-$ROOT_DIR}"
GENERATED_NODE_KEY=""
WIZARD_RAN=false
ACTION="install"
PURGE_REPO=false
ENV_BACKUP_DIR=""
RESTORE_ENV_AFTER_INSTALL=false

log() {
  if [[ "$NON_INTERACTIVE" == true ]] || [[ ! -t 1 ]]; then
    echo "[install] $*"
  else
    print_info "$*"
  fi
}

warn() {
  if [[ "$NON_INTERACTIVE" == true ]] || [[ ! -t 1 ]]; then
    echo "[install] ВНИМАНИЕ: $*" >&2
  else
    print_warn "$*"
  fi
}

die() {
  if [[ "$NON_INTERACTIVE" == true ]] || [[ ! -t 1 ]]; then
    echo "[install] ОШИБКА: $*" >&2
  else
    print_error "$*"
  fi
  exit 1
}

usage() {
  ui_show_help
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --with-daemon)
        WITH_DAEMON=true
        ;;
      --with-systemd)
        WITH_SYSTEMD=true
        ;;
      --with-node-agent)
        WITH_NODE_AGENT=true
        ;;
      --force)
        FORCE=true
        ;;
      --non-interactive)
        NON_INTERACTIVE=true
        ;;
      -y|--yes)
        ACCEPT_DEFAULTS=true
        ;;
      --uninstall)
        ACTION="uninstall"
        ;;
      --purge)
        PURGE_REPO=true
        if [[ "$ACTION" == "install" ]]; then
          ACTION="uninstall"
        fi
        ;;
      --reinstall)
        ACTION="reinstall"
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        die "Неизвестный аргумент: $1 (см. --help)"
        ;;
    esac
    shift
  done
}

prompt_yes_no() {
  local prompt="$1"
  local default="${2:-n}"
  local answer=""

  if [[ "$ACCEPT_DEFAULTS" == true ]]; then
    [[ "$default" == "y" ]]
    return $?
  fi

  if [[ "$default" == "y" ]]; then
    read -r -p "$prompt [Y/n]: " answer
    answer="${answer:-y}"
  else
    read -r -p "$prompt [y/N]: " answer
    answer="${answer:-n}"
  fi
  [[ "$answer" == "y" || "$answer" == "Y" || "$answer" == "yes" || "$answer" == "да" ]]
}

show_main_menu() {
  local choice=""
  while true; do
    ui_show_main_menu
    read -r -p "Выберите пункт [1]: " choice
    choice="${choice:-1}"
    case "$choice" in
      1)
        return 0
        ;;
      2)
        run_reinstall_action
        exit $?
        ;;
      3)
        run_uninstall_action
        exit $?
        ;;
      4)
        usage
        exit 0
        ;;
      *)
        print_warn "Неизвестный пункт: $choice"
        ;;
    esac
  done
}

collect_uninstall_options() {
  local -n _out_args=$1
  _out_args=(--purge-state --remove-system-config)

  if [[ "$NON_INTERACTIVE" == true ]]; then
    _out_args+=(--remove-nginx --yes)
    if [[ "$PURGE_REPO" == true ]]; then
      _out_args+=(--purge)
    fi
    return 0
  fi

  if [[ "$ACCEPT_DEFAULTS" == true ]]; then
    _out_args+=(--remove-nginx --yes)
    if [[ "$PURGE_REPO" == true ]]; then
      _out_args+=(--purge)
    fi
    return 0
  fi

  ui_show_banner
  ui_section "Полное удаление AdminPanelAZ"
  ui_warn_box "Внимание" \
    "Будут остановлены systemd-сервисы, daemon/watchdog и удалены unit-файлы." \
    "Данные AntiZapret (/root/antizapret и др.) НЕ удаляются."
  echo

  if ui_confirm "Удалить конфигурацию nginx сайта панели?" "y"; then
    _out_args+=(--remove-nginx)
  fi
  if ui_confirm "Удалить правила firewall AdminPanelAZ (ufw)?" "n"; then
    _out_args+=(--remove-firewall)
  fi
  if ui_confirm "Удалить backend/.env и node_agent.env?" "n" "true"; then
    _out_args+=(--remove-env)
  fi
  if [[ "$PURGE_REPO" == true ]] || ui_confirm "Удалить каталог проекта $ROOT_DIR (--purge)?" "n" "true"; then
    _out_args+=(--purge)
    PURGE_REPO=true
  fi
}

run_uninstall_action() {
  resolve_project_dir
  ensure_executable_scripts

  local -a uninstall_args=()
  collect_uninstall_options uninstall_args

  log "Запуск удаления..."
  "$ROOT_DIR/scripts/uninstall.sh" "${uninstall_args[@]}"
}

backup_env_for_reinstall() {
  ENV_BACKUP_DIR=""
  local stamp
  stamp="$(date +%Y%m%d-%H%M%S)"
  ENV_BACKUP_DIR="$ROOT_DIR/.reinstall-backup/$stamp"
  mkdir -p "$ENV_BACKUP_DIR"

  if [[ -f "$ENV_FILE" ]]; then
    cp -a "$ENV_FILE" "$ENV_BACKUP_DIR/.env"
    log "Резервная копия: $ENV_BACKUP_DIR/.env"
  fi
  if [[ -f "$NODE_ENV_FILE" ]]; then
    cp -a "$NODE_ENV_FILE" "$ENV_BACKUP_DIR/node_agent.env"
    log "Резервная копия: $ENV_BACKUP_DIR/node_agent.env"
  fi
}

offer_restore_env_backup() {
  if [[ -z "$ENV_BACKUP_DIR" || ! -d "$ENV_BACKUP_DIR" ]]; then
    return 0
  fi
  if [[ "$RESTORE_ENV_AFTER_INSTALL" == true ]]; then
    restore_env_backup
    return 0
  fi
  if [[ "$NON_INTERACTIVE" == true ]]; then
    return 0
  fi
  if ! prompt_yes_no "Восстановить backend/.env из резервной копии переустановки?" "n"; then
    log "Конфигурация из мастера сохранена. Резервная копия: $ENV_BACKUP_DIR"
    return 0
  fi
  restore_env_backup
}

restore_env_backup() {
  if [[ -f "$ENV_BACKUP_DIR/.env" ]]; then
    cp -a "$ENV_BACKUP_DIR/.env" "$ENV_FILE"
    log "Восстановлен backend/.env из $ENV_BACKUP_DIR"
  fi
  if [[ -f "$ENV_BACKUP_DIR/node_agent.env" ]]; then
    cp -a "$ENV_BACKUP_DIR/node_agent.env" "$NODE_ENV_FILE"
    log "Восстановлен backend/node_agent.env из $ENV_BACKUP_DIR"
  fi
}

run_reinstall_action() {
  resolve_project_dir
  ensure_executable_scripts

  if [[ "$NON_INTERACTIVE" != true && "$ACCEPT_DEFAULTS" != true && -t 0 ]]; then
    ui_show_banner
    ui_section "Переустановка AdminPanelAZ"
    ui_info_box "" \
      "Резервная копия .env → удаление сервисов и состояния → новая установка."
    echo
    if ! ui_confirm "Продолжить переустановку?" "n"; then
      print_info "Переустановка отменена."
      exit 0
    fi
  fi

  backup_env_for_reinstall

  local -a uninstall_args=(--purge-state --remove-nginx --remove-system-config --skip-confirm)
  if [[ "$NON_INTERACTIVE" == true || "$ACCEPT_DEFAULTS" == true ]]; then
    uninstall_args+=(--yes)
  fi

  log "Удаление перед переустановкой..."
  "$ROOT_DIR/scripts/uninstall.sh" "${uninstall_args[@]}"

  ACTION="install"
  run_install_flow
  offer_restore_env_backup
}

should_run_wizard() {
  if [[ "$NON_INTERACTIVE" == true ]]; then
    return 1
  fi
  if [[ -t 0 ]]; then
    return 0
  fi
  if [[ "$ACCEPT_DEFAULTS" == true ]]; then
    return 0
  fi
  return 1
}

run_wizard_if_needed() {
  if ! should_run_wizard; then
    return 0
  fi

  # shellcheck source=scripts/install-wizard.sh
  source "$ROOT_DIR/scripts/install-wizard.sh"
  WIZ_ACCEPT_DEFAULTS="$ACCEPT_DEFAULTS"
  run_install_wizard
  WIZARD_RAN=true
  FORCE=true
}

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
      log "Перезапуск с sudo..."
      exec sudo -E "$0" "$@"
    fi
    die "Запустите от root: sudo $0"
  fi
}

check_os() {
  if [[ ! -f /etc/os-release ]]; then
    warn "Не удалось определить ОС (/etc/os-release отсутствует)"
    return
  fi

  # shellcheck source=/dev/null
  source /etc/os-release
  local supported=false

  case "${ID:-}" in
    ubuntu)
      if [[ "${VERSION_ID:-}" == "24.04" ]] || [[ "${VERSION_ID:-}" > "24.04" ]]; then
        supported=true
      fi
      ;;
    debian)
      if [[ "${VERSION_ID:-}" -ge 13 ]] 2>/dev/null || [[ "${VERSION_CODENAME:-}" == "trixie" ]] || [[ "${VERSION_CODENAME:-}" == "forky" ]]; then
        supported=true
      fi
      ;;
  esac

  if [[ "$supported" == true ]]; then
    log "ОС: ${PRETTY_NAME:-unknown} — поддерживается"
  else
    warn "ОС ${PRETTY_NAME:-unknown} не в списке протестированных (Ubuntu 24.04 / Debian 13+). Продолжаем на свой риск."
  fi
}

check_antizapret() {
  if [[ "$WIZARD_RAN" == true ]]; then
    return 0
  fi

  local az_path="${ANTIZAPRET_PATH:-/root/antizapret}"
  if [[ -d "$az_path" && -f "$az_path/client.sh" ]]; then
    log "AntiZapret найден: $az_path"
  else
    warn "Каталог AntiZapret не найден ($az_path). Панель запустится, но VPN-функции будут ограничены."
    warn "Установите AntiZapret: https://github.com/GubernievS/AntiZapret-VPN"
  fi
}

random_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

node_major_version() {
  if ! command -v node >/dev/null 2>&1; then
    echo 0
    return
  fi
  node -v | sed 's/^v//' | cut -d. -f1
}

install_nodejs() {
  local major
  major="$(node_major_version)"
  if [[ "$major" -ge 18 ]]; then
    log "Node.js $(node -v) — OK"
    return
  fi

  log "Установка Node.js 18+..."
  if apt-cache show nodejs 2>/dev/null | grep -q '^Version: 18\|^Version: 20\|^Version: 22'; then
    apt-get install -y nodejs npm
    major="$(node_major_version)"
    if [[ "$major" -ge 18 ]]; then
      log "Node.js $(node -v) установлен из apt"
      return
    fi
  fi

  log "Подключение NodeSource (Node.js 20.x)..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
  major="$(node_major_version)"
  if [[ "$major" -lt 18 ]]; then
    die "Не удалось установить Node.js 18+ (текущая версия: $(node -v 2>/dev/null || echo 'нет'))"
  fi
  log "Node.js $(node -v) установлен"
}

install_system_deps() {
  ui_progress_start "Установка системных зависимостей"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    git \
    curl \
    build-essential \
    ca-certificates \
    pkg-config \
    libffi-dev \
    libssl-dev

  install_nodejs
  ui_progress_done "Системные зависимости"
}

resolve_project_dir() {
  if [[ -f "$ROOT_DIR/start.sh" && -f "$ROOT_DIR/backend/requirements.txt" ]]; then
    INSTALL_TARGET="$ROOT_DIR"
    return
  fi

  if [[ -n "$INSTALL_FROM_GIT" ]]; then
    log "Клонирование из $INSTALL_FROM_GIT в $INSTALL_TARGET..."
    mkdir -p "$(dirname "$INSTALL_TARGET")"
    if [[ -d "$INSTALL_TARGET/.git" ]]; then
      log "Репозиторий уже существует, обновление (git pull)..."
      git -C "$INSTALL_TARGET" pull --ff-only || warn "git pull не удался, используем существующую копию"
    elif [[ -d "$INSTALL_TARGET" ]]; then
      die "Каталог $INSTALL_TARGET существует, но это не git-репозиторий AdminPanelAZ"
    else
      git clone "$INSTALL_FROM_GIT" "$INSTALL_TARGET"
    fi
    ROOT_DIR="$INSTALL_TARGET"
    BACKEND_DIR="$ROOT_DIR/backend"
    FRONTEND_DIR="$ROOT_DIR/frontend"
    VENV_DIR="$BACKEND_DIR/.venv"
    ENV_FILE="$BACKEND_DIR/.env"
    ENV_EXAMPLE="$BACKEND_DIR/.env.example"
    NODE_ENV_FILE="$BACKEND_DIR/node_agent.env"
    return
  fi

  die "Запустите скрипт из каталога проекта или задайте INSTALL_FROM_GIT=<url>"
}

ensure_executable_scripts() {
  chmod +x "$ROOT_DIR/start.sh" "$ROOT_DIR/start_node_agent.sh" 2>/dev/null || true
  chmod +x "$ROOT_DIR/scripts/"*.sh 2>/dev/null || true
  chmod +x "$ROOT_DIR/scripts/nginx-setup.sh" "$ROOT_DIR/scripts/nginx-common.sh" "$ROOT_DIR/scripts/firewall-setup.sh" 2>/dev/null || true
}

env_get() {
  local key="$1"
  if [[ ! -f "$ENV_FILE" ]]; then
    return 1
  fi
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true
}

env_set() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >>"$ENV_FILE"
  fi
}

node_env_set() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$NODE_ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$NODE_ENV_FILE"
  else
    echo "${key}=${value}" >>"$NODE_ENV_FILE"
  fi
}

is_placeholder_secret() {
  local value="$1"
  [[ -z "$value" ]] && return 0
  case "$value" in
    change-me*|CHANGE-ME*|your-secret*|YOUR-SECRET*)
      return 0
      ;;
  esac
  return 1
}

install_controller_selected() {
  if [[ "$WIZARD_RAN" == true ]]; then
    wizard_install_controller
    return $?
  fi
  return 0
}

install_node_selected() {
  if [[ "$WIZARD_RAN" == true ]]; then
    wizard_install_node
    return $?
  fi
  [[ "$WITH_NODE_AGENT" == true ]]
}

setup_env() {
  if ! install_controller_selected; then
    log "Режим node-only: пропуск backend/.env"
    return 0
  fi

  if [[ ! -f "$ENV_EXAMPLE" ]]; then
    die "Не найден $ENV_EXAMPLE"
  fi

  if [[ -f "$ENV_FILE" && "$FORCE" != true ]]; then
    log "backend/.env уже существует — не перезаписываем (флаг --force для перезаписи)"
  elif [[ -f "$ENV_FILE" && "$FORCE" == true ]]; then
    log "Перезапись backend/.env из .env.example (--force)"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
  else
    log "Создание backend/.env из .env.example"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
  fi

  local secret_key
  secret_key="$(env_get SECRET_KEY)"
  if is_placeholder_secret "$secret_key"; then
    secret_key="$(random_hex)"
    env_set SECRET_KEY "$secret_key"
    log "Сгенерирован SECRET_KEY"
  fi

  if [[ "$WIZARD_RAN" == true ]]; then
    env_set APP_ENV "$WIZ_APP_ENV"
    env_set ANTIZAPRET_PATH "$WIZ_ANTIZAPRET_PATH"
    env_set CORS_ORIGINS "$WIZ_CORS_ORIGINS"
    env_set ALLOW_INTERNAL_NODES "$WIZ_ALLOW_INTERNAL_NODES"
    env_set DEFAULT_ADMIN_USERNAME "$WIZ_ADMIN_USERNAME"
    env_set DEFAULT_ADMIN_PASSWORD "$WIZ_ADMIN_PASSWORD"
    env_set DEFAULT_ADMIN_MUST_CHANGE_PASSWORD "$WIZ_ADMIN_MUST_CHANGE_PASSWORD"
    env_set BACKEND_HOST "$WIZ_BACKEND_HOST"
    env_set BACKEND_PORT "$WIZ_BACKEND_PORT"
    if [[ "${WIZ_BEHIND_NGINX:-false}" == "true" ]]; then
      env_set BEHIND_NGINX "true"
      env_set TRUSTED_PROXY_IPS "127.0.0.1,::1"
      env_set FORWARDED_ALLOW_IPS "127.0.0.1,::1"
    fi
    if [[ "${WIZ_UVICORN_WORKERS:-1}" -gt 1 ]]; then
      env_set UVICORN_WORKERS "$WIZ_UVICORN_WORKERS"
    fi
    env_set BACKUP_ROOT "$WIZ_BACKUP_ROOT"
    env_set CIDR_DB_REFRESH_ENABLED "$WIZ_CIDR_DB_REFRESH_ENABLED"
    env_set CIDR_DB_REFRESH_HOUR "$WIZ_CIDR_DB_REFRESH_HOUR"
    env_set CIDR_DB_REFRESH_MINUTE "$WIZ_CIDR_DB_REFRESH_MINUTE"
    env_set TRAFFIC_SYNC_ENABLED "$WIZ_TRAFFIC_SYNC_ENABLED"
    env_set NODE_AGENT_PORT "$WIZ_NODE_AGENT_PORT"
    if [[ "$WIZ_ENFORCE_PASSWORD_POLICY" == true ]]; then
      env_set ENFORCE_PASSWORD_POLICY "true"
    fi
    if [[ "$WIZ_APP_ENV" == "production" ]]; then
      env_set AUTH_RATE_LIMIT_ENABLED "true"
      env_set SECURITY_HEADERS_ENABLED "true"
      env_set AUDIT_LOG_ENABLED "true"
    fi
    if [[ -n "$WIZ_NODE_AGENT_API_KEY" ]]; then
      env_set NODE_AGENT_API_KEY "$WIZ_NODE_AGENT_API_KEY"
    fi
    if [[ -n "${WIZ_AUTH_RATE_LIMIT_BACKEND:-}" ]]; then
      env_set AUTH_RATE_LIMIT_BACKEND "$WIZ_AUTH_RATE_LIMIT_BACKEND"
    fi
    if [[ -n "${WIZ_REDIS_URL:-}" ]]; then
      env_set REDIS_URL "$WIZ_REDIS_URL"
    fi
    if [[ "${WIZ_NODE_AGENT_MTLS_ENABLED:-false}" == "true" ]]; then
      env_set NODE_AGENT_MTLS_ENABLED "true"
    fi
    if [[ -n "${WIZ_NODE_API_KEY_ROTATION_DAYS:-}" && "${WIZ_NODE_API_KEY_ROTATION_DAYS:-0}" != "0" ]]; then
      env_set NODE_API_KEY_ROTATION_DAYS "$WIZ_NODE_API_KEY_ROTATION_DAYS"
    fi
    if [[ "$WIZ_APP_ENV" == "production" ]]; then
      env_set REFRESH_TOKEN_COOKIE_SECURE "true"
    fi
  else
    local az_path="${ANTIZAPRET_PATH:-/root/antizapret}"
    env_set ANTIZAPRET_PATH "$az_path"

    local backend_port="${BACKEND_PORT:-8000}"
    env_set CORS_ORIGINS "http://127.0.0.1:${backend_port},http://localhost:${backend_port},http://127.0.0.1:5173,http://localhost:5173"
    env_set BACKEND_HOST "127.0.0.1"
  fi

  if [[ -f "$ROOT_DIR/scripts/env_defaults.sh" ]]; then
    # shellcheck source=scripts/env_defaults.sh
    source "$ROOT_DIR/scripts/env_defaults.sh"
    ensure_env_defaults
    log "Добавлены значения по умолчанию из scripts/env_defaults.sh (AdminAntizapret 1.9.0)"
  fi

  mkdir -p "$BACKEND_DIR/data" "${WIZ_BACKUP_ROOT:-/var/backups/adminpanelaz}"
}

setup_node_env() {
  if ! install_node_selected; then
    return 0
  fi

  log "Создание $NODE_ENV_FILE"
  if [[ -f "$NODE_ENV_EXAMPLE" ]]; then
    cp "$NODE_ENV_EXAMPLE" "$NODE_ENV_FILE"
  else
    : >"$NODE_ENV_FILE"
  fi
  chmod 600 "$NODE_ENV_FILE"

  local api_key="${WIZ_NODE_AGENT_API_KEY:-${NODE_AGENT_API_KEY:-}}"
  if [[ -z "$api_key" ]] || is_placeholder_secret "$api_key"; then
    api_key="$(random_hex)"
    log "Сгенерирован NODE_AGENT_API_KEY"
  fi

  local az_path="${WIZ_ANTIZAPRET_PATH:-${ANTIZAPRET_PATH:-/root/antizapret}}"
  local node_port="${WIZ_NODE_AGENT_PORT:-${NODE_AGENT_PORT:-9100}}"
  local node_state="${WIZ_NODE_STATE_DIR:-${NODE_AGENT_STATE_DIR:-$ROOT_DIR/.runtime/node}}"

  node_env_set NODE_AGENT_API_KEY "$api_key"
  node_env_set ANTIZAPRET_PATH "$az_path"
  node_env_set NODE_AGENT_PORT "$node_port"
  node_env_set NODE_AGENT_STATE_DIR "$node_state"
  node_env_set NODE_AGENT_HOST "0.0.0.0"
  node_env_set NODE_AGENT_MODE "prod"

  local allowed_ips="${WIZ_NODE_AGENT_ALLOWED_IPS:-}"
  if [[ -n "$allowed_ips" ]]; then
    node_env_set NODE_AGENT_ALLOWED_IPS "$allowed_ips"
  fi
  if [[ "${WIZ_NODE_AGENT_MTLS_ENABLED:-false}" == "true" ]]; then
    node_env_set NODE_AGENT_MTLS_ENABLED "true"
  fi

  GENERATED_NODE_KEY="$api_key"
  export NODE_AGENT_API_KEY="$api_key"
}

setup_backend() {
  ui_progress_start "Настройка backend (Python venv)"
  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
    log "Создано виртуальное окружение: $VENV_DIR"
  else
    log "Виртуальное окружение уже существует"
  fi

  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  pip install -q --upgrade pip
  pip install -q -r "$BACKEND_DIR/requirements.txt"
  mkdir -p "$BACKEND_DIR/data"
  ui_progress_done "Backend (Python venv)"
}

seed_wizard_db_settings() {
  if [[ "$WIZARD_RAN" != true ]] || ! install_controller_selected; then
    return 0
  fi
  if [[ "$WIZ_TELEGRAM_ENABLED" != true && "$WIZ_AUTO_BACKUP_ENABLED" != true ]]; then
    return 0
  fi

  log "Применение настроек мастера в БД (Telegram, auto-backup)..."
  WIZ_TELEGRAM_ENABLED="$WIZ_TELEGRAM_ENABLED" \
  WIZ_TELEGRAM_BOT_TOKEN="$WIZ_TELEGRAM_BOT_TOKEN" \
  WIZ_TELEGRAM_CHAT_ID="$WIZ_TELEGRAM_CHAT_ID" \
  WIZ_AUTO_BACKUP_ENABLED="$WIZ_AUTO_BACKUP_ENABLED" \
  WIZ_AUTO_BACKUP_DAYS="$WIZ_AUTO_BACKUP_DAYS" \
    "$VENV_DIR/bin/python" "$ROOT_DIR/scripts/seed-wizard-db.py" || warn "Не удалось записать настройки в БД"
}

setup_frontend() {
  if ! install_controller_selected; then
    log "Режим node-only: пропуск сборки frontend"
    return 0
  fi

  ui_progress_start "Настройка frontend (npm install)"
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    (cd "$FRONTEND_DIR" && npm install)
  else
    print_info "node_modules уже существует, npm install пропущен (удалите node_modules для полной переустановки)"
  fi
  ui_progress_done "Frontend (npm install)"

  ui_progress_start "Сборка frontend (npm run build)"
  (cd "$FRONTEND_DIR" && npm run build)
  ui_progress_done "Frontend собран: $FRONTEND_DIR/dist"
}

setup_runtime_dirs() {
  local state_dir="${ADMINPANELAZ_STATE_DIR:-${WIZ_STATE_DIR:-$ROOT_DIR/.runtime}}"
  if install_controller_selected; then
    mkdir -p "$state_dir/logs" "$state_dir/run"
  fi
  if install_node_selected; then
    local node_state="${NODE_AGENT_STATE_DIR:-${WIZ_NODE_STATE_DIR:-$ROOT_DIR/.runtime/node}}"
    mkdir -p "$node_state/logs" "$node_state/run"
  fi
}

setup_systemd() {
  if ! install_controller_selected; then
    return 0
  fi

  log "Установка systemd unit для controller..."
  INSTALL_FROM_INSTALL_SH=1 \
    INSTALL_USER="${INSTALL_USER:-root}" \
    ADMINPANELAZ_STATE_DIR="${ADMINPANELAZ_STATE_DIR:-${WIZ_STATE_DIR:-/var/lib/adminpanelaz}}" \
    BACKEND_HOST="${BACKEND_HOST:-${WIZ_BACKEND_HOST:-127.0.0.1}}" \
    BACKEND_PORT="${BACKEND_PORT:-${WIZ_BACKEND_PORT:-8000}}" \
    UVICORN_WORKERS="${UVICORN_WORKERS:-${WIZ_UVICORN_WORKERS:-1}}" \
    "$ROOT_DIR/scripts/install-systemd.sh"
}

setup_node_agent_systemd() {
  if ! install_node_selected; then
    return 0
  fi

  local api_key="${GENERATED_NODE_KEY:-${NODE_AGENT_API_KEY:-}}"
  if is_placeholder_secret "$api_key"; then
    api_key="$(random_hex)"
    log "Сгенерирован NODE_AGENT_API_KEY для node agent"
    node_env_set NODE_AGENT_API_KEY "$api_key"
  fi

  log "Установка systemd unit для node agent..."
  INSTALL_FROM_INSTALL_SH=1 \
    INSTALL_USER="${INSTALL_USER:-root}" \
    NODE_AGENT_STATE_DIR="${NODE_AGENT_STATE_DIR:-${WIZ_NODE_STATE_DIR:-/var/lib/adminpanelaz-node}}" \
    NODE_AGENT_PORT="${NODE_AGENT_PORT:-${WIZ_NODE_AGENT_PORT:-9100}}" \
    NODE_AGENT_API_KEY="$api_key" \
    "$ROOT_DIR/scripts/install-node-systemd.sh"

  GENERATED_NODE_KEY="$api_key"
}

start_daemon() {
  if ! install_controller_selected; then
    return 0
  fi

  log "Запуск prod daemon..."
  BACKEND_HOST="${BACKEND_HOST:-${WIZ_BACKEND_HOST:-127.0.0.1}}" \
  BACKEND_PORT="${BACKEND_PORT:-${WIZ_BACKEND_PORT:-8000}}" \
  UVICORN_WORKERS="${UVICORN_WORKERS:-${WIZ_UVICORN_WORKERS:-1}}" \
  ADMINPANELAZ_STATE_DIR="${ADMINPANELAZ_STATE_DIR:-${WIZ_STATE_DIR:-$ROOT_DIR/.runtime}}" \
    ADMINPANELAZ_MODE=prod "$ROOT_DIR/start.sh" daemon
}

ddns_config_quote() {
  local value="$1"
  value="${value//\'/\'\\\'\'}"
  printf "'%s'" "$value"
}

write_ddns_config() {
  local provider="${WIZ_DDNS_PROVIDER:-none}"
  local config_dir="/etc/adminpanelaz"
  local config_file="$config_dir/ddns.env"

  [[ "$provider" != "none" && -n "$provider" ]] || return 0

  mkdir -p "$config_dir"
  chmod 700 "$config_dir"

  local domain=""
  case "$provider" in
    duckdns)
      domain="${WIZ_DDNS_SUBDOMAIN}.duckdns.org"
      ;;
    noip)
      domain="${WIZ_DDNS_HOSTNAME}"
      ;;
  esac

  {
    echo "# AdminPanelAZ DDNS (создан install.sh)"
    echo "DDNS_PROVIDER=$(ddns_config_quote "$provider")"
    echo "DDNS_DOMAIN=$(ddns_config_quote "$domain")"
    case "$provider" in
      duckdns)
        echo "DDNS_SUBDOMAIN=$(ddns_config_quote "$WIZ_DDNS_SUBDOMAIN")"
        echo "DDNS_TOKEN=$(ddns_config_quote "$WIZ_DDNS_TOKEN")"
        ;;
      noip)
        echo "DDNS_HOSTNAME=$(ddns_config_quote "$WIZ_DDNS_HOSTNAME")"
        echo "DDNS_USERNAME=$(ddns_config_quote "$WIZ_DDNS_USERNAME")"
        echo "DDNS_PASSWORD=$(ddns_config_quote "$WIZ_DDNS_PASSWORD")"
        ;;
    esac
  } >"$config_file"

  chmod 600 "$config_file"
  log "DDNS конфигурация: $config_file ($domain)"
}

setup_ddns_if_selected() {
  if [[ "$WIZARD_RAN" != true ]] || ! install_controller_selected; then
    return 0
  fi

  local provider="${WIZ_DDNS_PROVIDER:-none}"
  if [[ "$provider" == "none" || -z "$provider" ]]; then
    return 0
  fi

  log "Настройка DDNS ($provider)..."
  write_ddns_config

  if [[ ! -x "$ROOT_DIR/scripts/ddns-update.sh" ]]; then
    chmod +x "$ROOT_DIR/scripts/ddns-update.sh"
  fi

  if "$ROOT_DIR/scripts/ddns-update.sh" update; then
    log "DDNS: начальное обновление IP выполнено"
  else
    warn "DDNS: не удалось обновить IP — проверьте token/учётные данные и доступ в интернет"
    if [[ "${WIZ_NGINX_MODE:-none}" == "le" ]]; then
      warn "Let's Encrypt может не выдать сертификат, пока DNS не указывает на этот сервер"
    fi
  fi

  if [[ "${WIZ_DDNS_CONFIGURE_UPDATE:-false}" == "true" ]]; then
    if "$ROOT_DIR/scripts/ddns-update.sh" install-timer; then
      log "DDNS: systemd timer установлен (каждые 5 минут)"
    else
      warn "DDNS: не удалось установить timer — запускайте вручную: sudo ./scripts/ddns-update.sh update"
    fi
  fi
}

setup_nginx_if_selected() {
  if [[ "$WIZARD_RAN" != true ]] || ! install_controller_selected; then
    return 0
  fi

  local mode="${WIZ_NGINX_MODE:-none}"
  if [[ "$mode" == "none" ]]; then
    return 0
  fi

  log "Настройка публикации (Nginx/HTTPS): $mode"

  # shellcheck source=scripts/nginx-common.sh
  source "$ROOT_DIR/scripts/nginx-common.sh"
  nginx_common_init

  local backend_port="${WIZ_BACKEND_PORT:-8000}"
  local domain="${WIZ_NGINX_DOMAIN:-}"
  local https_port="${WIZ_HTTPS_PUBLIC_PORT:-443}"
  local http_port="${WIZ_HTTP_ACME_PORT:-80}"

  case "$mode" in
    http_direct)
      nginx_apply_direct_http_env "$backend_port"
      nginx_remove_site "$(nginx_env_get DOMAIN)"
      log "HTTP без nginx: http://<сервер>:${backend_port}/ (не рекомендуется для интернета)"
      ;;
    le)
      [[ -n "$domain" ]] || die "Для Let's Encrypt нужен домен (запустите install.sh заново или ./scripts/nginx-setup.sh)"
      nginx_ensure_nginx || die "Не удалось установить nginx"
      nginx_obtain_letsencrypt_cert "$domain" "${WIZ_NGINX_EMAIL:-}"
      local cert="/etc/letsencrypt/live/${domain}/fullchain.pem"
      local key="/etc/letsencrypt/live/${domain}/privkey.pem"
      local conf
      conf="$(nginx_render_template \
        "$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template" \
        "$domain" "$backend_port" "$cert" "$key" "$https_port" "$http_port")"
      nginx_install_site "$conf" "$domain"
      nginx_apply_behind_proxy_env "$domain" "$backend_port" "https"
      if [[ "$WIZ_APP_ENV" == "production" ]]; then
        nginx_env_set ENFORCE_HTTPS "true"
      fi
      systemctl enable --now snap.certbot.renew.timer 2>/dev/null || \
        systemctl enable --now certbot.timer 2>/dev/null || true
      log "Nginx + Let's Encrypt: https://${domain}:${https_port}/"
      ;;
    selfsigned)
      [[ -n "$domain" ]] || domain="$(hostname -f 2>/dev/null || hostname)"
      nginx_ensure_nginx || die "Не удалось установить nginx"
      mkdir -p /etc/ssl/private
      if [[ ! -f "$NGINX_SELF_SIGNED_CERT" ]]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
          -keyout "$NGINX_SELF_SIGNED_KEY" \
          -out "$NGINX_SELF_SIGNED_CERT" \
          -subj "/CN=${domain}" >/dev/null 2>&1
      fi
      local conf
      conf="$(nginx_render_template \
        "$NGINX_TEMPLATE_DIR/adminpanelaz.conf.template" \
        "$domain" "$backend_port" "$NGINX_SELF_SIGNED_CERT" "$NGINX_SELF_SIGNED_KEY" \
        "$https_port" "$http_port")"
      nginx_install_site "$conf" "$domain"
      nginx_apply_behind_proxy_env "$domain" "$backend_port" "https"
      if [[ "$WIZ_APP_ENV" == "production" ]]; then
        nginx_env_set ENFORCE_HTTPS "true"
      fi
      log "Nginx + самоподписанный SSL: https://${domain}:${https_port}/"
      ;;
    *)
      warn "Неизвестный режим Nginx: $mode — пропуск"
      return 0
      ;;
  esac
}

restart_services_after_nginx() {
  if [[ "${WIZ_NGINX_MODE:-none}" == "none" ]]; then
    return 0
  fi
  if ! install_controller_selected; then
    return 0
  fi
  if [[ "$WITH_SYSTEMD" == true ]]; then
    systemctl restart adminpanelaz 2>/dev/null || true
  elif [[ "$WITH_DAEMON" == true ]]; then
    "$ROOT_DIR/start.sh" restart 2>/dev/null || true
  fi
}

setup_firewall_if_selected() {
  if [[ "$WIZARD_RAN" != true ]] || [[ "${WIZ_CONFIGURE_FIREWALL:-false}" != true ]]; then
    return 0
  fi

  log "Настройка firewall..."
  # shellcheck source=scripts/firewall-setup.sh
  source "$ROOT_DIR/scripts/firewall-setup.sh"

  local has_nginx=false
  local has_node=false
  local has_controller=false

  if install_controller_selected; then
    has_controller=true
  fi
  if install_node_selected; then
    has_node=true
  fi
  if [[ "${WIZ_NGINX_MODE:-none}" == "le" || "${WIZ_NGINX_MODE:-none}" == "selfsigned" ]]; then
    has_nginx=true
  fi

  local panel_ip="${WIZ_NODE_AGENT_ALLOWED_IPS:-}"
  if [[ -z "$panel_ip" ]]; then
    panel_ip="${WIZ_SERVER_ADDRESS:-}"
    panel_ip="${panel_ip#http://}"
    panel_ip="${panel_ip#https://}"
    panel_ip="${panel_ip%%/*}"
    panel_ip="${panel_ip%%:*}"
  else
    panel_ip="${panel_ip%%,*}"
    panel_ip="${panel_ip%%/*}"
  fi

  export FIREWALL_ENABLE_UFW="${WIZ_FIREWALL_ENABLE_UFW:-false}"

  local backend_port="${WIZ_BACKEND_PORT:-8000}"
  if [[ "$has_controller" != true ]]; then
    backend_port="0"
  fi

  firewall_show_rules_summary "$backend_port" "${WIZ_NODE_AGENT_PORT:-9100}" \
    "${WIZ_HTTPS_PUBLIC_PORT:-443}" "${WIZ_HTTP_ACME_PORT:-80}" \
    "$has_node" "$has_nginx" "$panel_ip" || true

  if [[ "$has_controller" == true ]]; then
    firewall_apply_rules "$backend_port" "${WIZ_NODE_AGENT_PORT:-9100}" \
      "${WIZ_HTTPS_PUBLIC_PORT:-443}" "${WIZ_HTTP_ACME_PORT:-80}" \
      "$has_node" "$has_nginx" "$panel_ip" || \
      warn "Не удалось применить правила firewall — см. SECURITY.md"
  elif [[ "$has_node" == true ]]; then
    firewall_apply_rules "0" "${WIZ_NODE_AGENT_PORT:-9100}" \
      "${WIZ_HTTPS_PUBLIC_PORT:-443}" "${WIZ_HTTP_ACME_PORT:-80}" \
      true false "$panel_ip" || \
      warn "Не удалось применить правила firewall — см. SECURITY.md"
  fi
}

start_node_agent_daemon() {
  if ! install_node_selected; then
    return 0
  fi

  local api_key="${1:-${GENERATED_NODE_KEY:-}}"
  if [[ -f "$NODE_ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    set -a
    source "$NODE_ENV_FILE"
    set +a
  fi
  if [[ -n "$api_key" ]]; then
    export NODE_AGENT_API_KEY="$api_key"
  fi
  log "Запуск node agent daemon..."
  NODE_AGENT_MODE=prod "$ROOT_DIR/start_node_agent.sh" daemon
}

print_post_install() {
  local backend_port="${BACKEND_PORT:-${WIZ_BACKEND_PORT:-8000}}"
  local node_port="${NODE_AGENT_PORT:-${WIZ_NODE_AGENT_PORT:-9100}}"
  local node_key="${1:-}"
  local admin_user="${WIZ_ADMIN_USERNAME:-admin}"
  local admin_pass="${WIZ_ADMIN_PASSWORD:-admin}"

  echo
  if [[ "$UI_USE_COLOR" == true ]]; then
    print_success "Установка AdminPanelAZ завершена"
  else
    echo "[install] Установка AdminPanelAZ завершена"
  fi
  echo
  ui_summary_title
  ui_summary_row "Каталог проекта" "$ROOT_DIR"

  if install_controller_selected; then
    ui_separator
    ui_bold "Учётные данные"
    echo
    ui_summary_row "Логин" "$admin_user"
    ui_summary_row "Пароль" "$admin_pass"
    print_info "Смените пароль при первом входе, если включена принудительная смена"
    echo
    ui_separator
    ui_bold "URL (prod / systemd)"
    echo
    ui_summary_row "UI + API" "http://127.0.0.1:${backend_port}/"
    ui_summary_row "API docs" "http://127.0.0.1:${backend_port}/docs"
    ui_summary_row "Конфигурация" "$ENV_FILE"
  fi

  if install_node_selected; then
    ui_summary_row "Node agent env" "$NODE_ENV_FILE"
  fi

  ui_summary_row "Логи (локально)" "${ADMINPANELAZ_STATE_DIR:-${WIZ_STATE_DIR:-$ROOT_DIR/.runtime}}/logs/"
  ui_summary_row "Логи (systemd)" "/var/lib/adminpanelaz/logs/"

  if install_controller_selected; then
    if [[ "${WIZ_DDNS_PROVIDER:-none}" != "none" ]]; then
      local ddns_domain=""
      case "${WIZ_DDNS_PROVIDER}" in
        duckdns) ddns_domain="${WIZ_DDNS_SUBDOMAIN}.duckdns.org" ;;
        noip) ddns_domain="${WIZ_DDNS_HOSTNAME}" ;;
      esac
      echo
      ui_separator
      ui_bold "DDNS (${WIZ_DDNS_PROVIDER})"
      echo
      ui_summary_row "Домен" "$ddns_domain"
      ui_summary_row "Обновление IP" "sudo ./scripts/ddns-update.sh update"
      ui_summary_row "Статус" "sudo ./scripts/ddns-update.sh status"
    fi
    echo
    ui_separator
    ui_bold "Публикация"
    echo
    if [[ "${WIZ_NGINX_MODE:-none}" != "none" && -n "${WIZ_NGINX_DOMAIN:-}" ]]; then
      local pub_https="${WIZ_HTTPS_PUBLIC_PORT:-443}"
      local url_suffix=""
      if [[ "$pub_https" != "443" ]]; then
        url_suffix=":${pub_https}"
      fi
      ui_summary_row "HTTPS" "https://${WIZ_NGINX_DOMAIN}${url_suffix}/"
    else
      print_info "Для интернета: sudo ./scripts/nginx-setup.sh или повторно sudo ./install.sh"
    fi
    echo
    ui_separator
    ui_bold "Управление controller"
    echo
    ui_info_box "" \
      "./start.sh              # dev, foreground" \
      "./start.sh daemon       # prod daemon + watchdog" \
      "./start.sh stop         # остановка" \
      "./start.sh status       # статус" \
      "systemctl start adminpanelaz    # если установлен systemd"
  fi

  if install_node_selected; then
    echo
    ui_separator
    ui_bold "Node agent"
    echo
    ui_info_box "" \
      "./start_node_agent.sh daemon" \
      "systemctl start adminpanelaz-node   # если установлен systemd" \
      "Порт: ${node_port}"
  fi

  if [[ -n "$node_key" ]]; then
    echo
    ui_separator
    ui_bold "NODE_AGENT_API_KEY (сохраните!)"
    echo
    if [[ "$UI_USE_COLOR" == true ]]; then
      echo "  $(ui_yellow "$node_key")"
    else
      echo "  $node_key"
    fi
  fi

  if [[ "$WIZARD_RAN" == true ]]; then
    echo
    ui_separator
    ui_bold "Firewall"
    echo
    if [[ "${WIZ_CONFIGURE_FIREWALL:-false}" == true ]]; then
      ui_info_box "" \
        "Правила применены (backend ${backend_port}/tcp закрыт с интернета;" \
        "HTTPS ${WIZ_HTTPS_PUBLIC_PORT:-443}, HTTP ${WIZ_HTTP_ACME_PORT:-80} открыты при Nginx)." \
        "Подробнее: SECURITY.md"
    else
      ui_info_box "Рекомендации" \
        "Backend ${backend_port}/tcp — только localhost (127.0.0.1)" \
        "Node agent ${node_port}/tcp — только IP панели" \
        "Наружу — HTTPS ${WIZ_HTTPS_PUBLIC_PORT:-443} (и HTTP ${WIZ_HTTP_ACME_PORT:-80} для ACME)" \
        "Подробнее: SECURITY.md"
    fi
  fi

  echo
  ui_separator
  ui_bold "Следующий шаг"
  echo
  if [[ "$WITH_SYSTEMD" == true ]]; then
    if install_controller_selected; then
      print_info "systemctl start adminpanelaz"
    fi
    if install_node_selected; then
      print_info "systemctl start adminpanelaz-node"
    fi
  elif [[ "$WITH_DAEMON" == true ]]; then
    print_info "Daemon запущен. Проверка: $ROOT_DIR/start.sh status"
  else
    local -a next_steps=("cd $ROOT_DIR")
    if install_controller_selected; then
      next_steps+=("sudo ./start.sh daemon          # prod controller")
    fi
    if install_node_selected; then
      next_steps+=("sudo ./start_node_agent.sh daemon")
    fi
    next_steps+=("# или: sudo ./install.sh --with-systemd")
    ui_info_box "Запуск вручную" "${next_steps[@]}"
  fi
  echo
}

main() {
  local original_argc=$#
  parse_args "$@"
  require_root "$@"

  if [[ "$ACTION" == "uninstall" ]]; then
    run_uninstall_action
    exit 0
  fi

  if [[ "$ACTION" == "reinstall" ]]; then
    run_reinstall_action
    exit 0
  fi

  if [[ "$original_argc" -eq 0 && -t 0 && "$NON_INTERACTIVE" != true ]]; then
    show_main_menu
  fi

  run_install_flow
}

run_install_flow() {
  check_os
  resolve_project_dir
  run_wizard_if_needed
  check_antizapret
  install_system_deps
  ensure_executable_scripts
  setup_env
  setup_node_env
  setup_backend
  seed_wizard_db_settings
  setup_frontend
  setup_runtime_dirs

  if install_controller_selected; then
    log "Примечание: backend запускается с правами root для интеграции с AntiZapret (client.sh, wg, systemctl)."
  fi

  if [[ "$WITH_SYSTEMD" == true ]]; then
    setup_systemd
    if install_controller_selected; then
      systemctl start adminpanelaz 2>/dev/null || warn "Не удалось запустить adminpanelaz (проверьте: systemctl status adminpanelaz)"
    fi
  elif [[ "$WITH_DAEMON" == true ]]; then
    start_daemon
  fi

  setup_ddns_if_selected
  setup_nginx_if_selected
  restart_services_after_nginx
  setup_firewall_if_selected

  if install_node_selected; then
    if [[ "$WITH_SYSTEMD" == true ]]; then
      setup_node_agent_systemd
      systemctl start adminpanelaz-node 2>/dev/null || warn "Не удалось запустить adminpanelaz-node"
    elif [[ "$WITH_DAEMON" == true ]]; then
      start_node_agent_daemon "$GENERATED_NODE_KEY"
    fi
  fi

  print_post_install "$GENERATED_NODE_KEY"
}

main "$@"
