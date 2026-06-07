#!/usr/bin/env bash
# Установка AdminPanelAZ на Ubuntu 24.04 / Debian 13+
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

log() {
  echo "[install] $*"
}

warn() {
  echo "[install] ВНИМАНИЕ: $*" >&2
}

die() {
  echo "[install] ОШИБКА: $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Использование: sudo ./install.sh [опции]

Опции:
  --with-daemon         Запустить prod daemon через start.sh после установки
  --with-systemd        Установить systemd unit (scripts/install-systemd.sh)
  --with-node-agent     Настроить node agent (+ install-node-systemd.sh с --with-systemd)
  --force               Перезаписать существующий backend/.env из .env.example
  --non-interactive     Без интерактивного мастера (флаги и переменные окружения)
  -y, --yes             Принять значения по умолчанию (для мастера или авто-подтверждение)
  --help                Показать эту справку

Переменные окружения:
  INSTALL_FROM_GIT      URL репозитория для клонирования (если скрипт запущен вне проекта)
  INSTALL_TARGET        Каталог установки при клонировании (по умолчанию — каталог скрипта)
  INSTALL_USER          Пользователь systemd-сервисов (по умолчанию root)

Интерактивный режим (по умолчанию при TTY):
  Мастер установки задаёт тип (controller / controller+node / node-only),
  сеть, администратора, node agent, systemd/daemon и опции .env.

Примеры:
  cd /opt/AdminPanelAZ && sudo ./install.sh
  sudo ./install.sh --with-systemd
  sudo ./install.sh --with-systemd --with-node-agent
  sudo ./install.sh --non-interactive --with-systemd
  sudo ./install.sh -y
  sudo INSTALL_FROM_GIT=https://github.com/user/AdminPanelAZ.git ./install.sh
EOF
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
  log "Установка системных зависимостей..."
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
    env_set ANTIZAPRET_PATH "$WIZ_ANTIZAPRET_PATH"
    env_set CORS_ORIGINS "$WIZ_CORS_ORIGINS"
    env_set ALLOW_INTERNAL_NODES "$WIZ_ALLOW_INTERNAL_NODES"
    env_set DEFAULT_ADMIN_USERNAME "$WIZ_ADMIN_USERNAME"
    env_set DEFAULT_ADMIN_PASSWORD "$WIZ_ADMIN_PASSWORD"
    env_set DEFAULT_ADMIN_MUST_CHANGE_PASSWORD "$WIZ_ADMIN_MUST_CHANGE_PASSWORD"
    env_set BACKEND_HOST "$WIZ_BACKEND_HOST"
    env_set BACKEND_PORT "$WIZ_BACKEND_PORT"
    env_set BACKUP_ROOT "$WIZ_BACKUP_ROOT"
    env_set CIDR_DB_REFRESH_ENABLED "$WIZ_CIDR_DB_REFRESH_ENABLED"
    env_set CIDR_DB_REFRESH_HOUR "$WIZ_CIDR_DB_REFRESH_HOUR"
    env_set CIDR_DB_REFRESH_MINUTE "$WIZ_CIDR_DB_REFRESH_MINUTE"
    env_set TRAFFIC_SYNC_ENABLED "$WIZ_TRAFFIC_SYNC_ENABLED"
    env_set NODE_AGENT_PORT "$WIZ_NODE_AGENT_PORT"
    if [[ -n "$WIZ_NODE_AGENT_API_KEY" ]]; then
      env_set NODE_AGENT_API_KEY "$WIZ_NODE_AGENT_API_KEY"
    fi
  else
    local az_path="${ANTIZAPRET_PATH:-/root/antizapret}"
    env_set ANTIZAPRET_PATH "$az_path"

    local backend_port="${BACKEND_PORT:-8000}"
    env_set CORS_ORIGINS "http://127.0.0.1:${backend_port},http://localhost:${backend_port},http://127.0.0.1:5173,http://localhost:5173"
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

  GENERATED_NODE_KEY="$api_key"
  export NODE_AGENT_API_KEY="$api_key"
}

setup_backend() {
  log "Настройка backend (Python venv)..."
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
  log "Зависимости backend установлены"
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

  log "Настройка frontend (npm)..."
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    (cd "$FRONTEND_DIR" && npm install)
  else
    log "node_modules уже существует, npm install пропущен (удалите node_modules для полной переустановки)"
  fi

  log "Сборка frontend (npm run build)..."
  (cd "$FRONTEND_DIR" && npm run build)
  log "Frontend собран: $FRONTEND_DIR/dist"
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
  INSTALL_USER="${INSTALL_USER:-root}" \
    ADMINPANELAZ_STATE_DIR="${ADMINPANELAZ_STATE_DIR:-${WIZ_STATE_DIR:-/var/lib/adminpanelaz}}" \
    BACKEND_HOST="${BACKEND_HOST:-${WIZ_BACKEND_HOST:-0.0.0.0}}" \
    BACKEND_PORT="${BACKEND_PORT:-${WIZ_BACKEND_PORT:-8000}}" \
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
  BACKEND_HOST="${BACKEND_HOST:-${WIZ_BACKEND_HOST:-0.0.0.0}}" \
  BACKEND_PORT="${BACKEND_PORT:-${WIZ_BACKEND_PORT:-8000}}" \
  ADMINPANELAZ_STATE_DIR="${ADMINPANELAZ_STATE_DIR:-${WIZ_STATE_DIR:-$ROOT_DIR/.runtime}}" \
    ADMINPANELAZ_MODE=prod "$ROOT_DIR/start.sh" daemon
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

  cat <<EOF

================================================================================
  AdminPanelAZ — установка завершена
================================================================================

Каталог проекта:  $ROOT_DIR

EOF

  if install_controller_selected; then
    cat <<EOF
Учётные данные:
  Логин:  ${admin_user}
  Пароль: ${admin_pass}
  (смените при первом входе, если включено принудительная смена пароля)

URL (prod / systemd):
  UI + API:  http://127.0.0.1:${backend_port}/
  API docs:  http://127.0.0.1:${backend_port}/docs

Конфигурация:     $ENV_FILE
EOF
  fi

  if install_node_selected; then
    echo "Node agent env:   $NODE_ENV_FILE"
  fi

  cat <<EOF
Логи (локально):  ${ADMINPANELAZ_STATE_DIR:-${WIZ_STATE_DIR:-$ROOT_DIR/.runtime}}/logs/
Логи (systemd):   /var/lib/adminpanelaz/logs/

EOF

  if install_controller_selected; then
    cat <<EOF
Управление controller:
  ./start.sh              # dev, foreground
  ./start.sh daemon       # prod daemon + watchdog
  ./start.sh stop         # остановка
  ./start.sh status       # статус
  systemctl start adminpanelaz    # если установлен systemd
  systemctl status adminpanelaz

EOF
  fi

  if install_node_selected; then
    cat <<EOF
Node agent:
  ./start_node_agent.sh daemon
  systemctl start adminpanelaz-node   # если установлен systemd
  Порт: ${node_port}

EOF
  fi

  if [[ -n "$node_key" ]]; then
    cat <<EOF
Сгенерированный NODE_AGENT_API_KEY (сохраните!):
  $node_key

EOF
  fi

  if [[ "$WITH_SYSTEMD" == true ]]; then
    if install_controller_selected; then
      echo "Systemd: systemctl start adminpanelaz"
    fi
    if install_node_selected; then
      echo "         systemctl start adminpanelaz-node"
    fi
    echo
  elif [[ "$WITH_DAEMON" == true ]]; then
    echo "Daemon запущен. Проверка: $ROOT_DIR/start.sh status"
    echo
  elif [[ "$WIZ_RUN_MODE:-manual}" == "manual" ]] || [[ "$WIZARD_RAN" != true ]]; then
    cat <<EOF
Следующий шаг:
  cd $ROOT_DIR
EOF
    if install_controller_selected; then
      echo "  sudo ./start.sh daemon          # prod controller"
    fi
    if install_node_selected; then
      echo "  sudo ./start_node_agent.sh daemon"
    fi
    echo "  # или"
    echo "  sudo ./install.sh --with-systemd"
    echo
  fi
}

main() {
  parse_args "$@"
  require_root "$@"
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
