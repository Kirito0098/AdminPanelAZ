#!/usr/bin/env bash
# Установка AdminPanelAZ на Ubuntu 24.04 / Debian 13+
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"

WITH_DAEMON=false
WITH_SYSTEMD=false
WITH_NODE_AGENT=false
FORCE=false
INSTALL_FROM_GIT="${INSTALL_FROM_GIT:-}"
INSTALL_TARGET="${INSTALL_TARGET:-$ROOT_DIR}"
GENERATED_NODE_KEY=""

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
  --with-daemon       Запустить prod daemon через start.sh после установки
  --with-systemd      Установить systemd unit (scripts/install-systemd.sh)
  --with-node-agent   Настроить node agent (+ install-node-systemd.sh с --with-systemd)
  --force             Перезаписать существующий backend/.env из .env.example
  --help              Показать эту справку

Переменные окружения:
  INSTALL_FROM_GIT    URL репозитория для клонирования (если скрипт запущен вне проекта)
  INSTALL_TARGET      Каталог установки при клонировании (по умолчанию — каталог скрипта)
  INSTALL_USER        Пользователь systemd-сервисов (по умолчанию root)

Примеры:
  cd /opt/AdminPanelAZ && sudo ./install.sh
  sudo ./install.sh --with-systemd
  sudo ./install.sh --with-systemd --with-node-agent
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
      # Debian 13+ (trixie и новее)
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

setup_env() {
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

  local az_path="${ANTIZAPRET_PATH:-/root/antizapret}"
  env_set ANTIZAPRET_PATH "$az_path"

  local backend_port="${BACKEND_PORT:-8000}"
  env_set CORS_ORIGINS "http://127.0.0.1:${backend_port},http://localhost:${backend_port},http://127.0.0.1:5173,http://localhost:5173"

  mkdir -p "$BACKEND_DIR/data" /var/backups/adminpanelaz
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

setup_frontend() {
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
  local state_dir="${ADMINPANELAZ_STATE_DIR:-$ROOT_DIR/.runtime}"
  mkdir -p "$state_dir/logs" "$state_dir/run"
  if [[ "$WITH_NODE_AGENT" == true ]]; then
    local node_state="${NODE_AGENT_STATE_DIR:-$ROOT_DIR/.runtime/node}"
    mkdir -p "$node_state/logs" "$node_state/run"
  fi
}

setup_systemd() {
  log "Установка systemd unit для controller..."
  INSTALL_USER="${INSTALL_USER:-root}" "$ROOT_DIR/scripts/install-systemd.sh"
}

setup_node_agent_systemd() {
  local api_key="${NODE_AGENT_API_KEY:-}"
  if is_placeholder_secret "$api_key"; then
    api_key="$(random_hex)"
    log "Сгенерирован NODE_AGENT_API_KEY для node agent"
  fi

  log "Установка systemd unit для node agent..."
  INSTALL_USER="${INSTALL_USER:-root}" NODE_AGENT_API_KEY="$api_key" \
    "$ROOT_DIR/scripts/install-node-systemd.sh"

  local unit="/etc/systemd/system/adminpanelaz-node.service"
  if [[ -f "$unit" ]] && grep -q 'change-me-node-agent-key' "$unit" 2>/dev/null; then
    sed -i "s|NODE_AGENT_API_KEY=change-me-node-agent-key|NODE_AGENT_API_KEY=${api_key}|" "$unit"
    systemctl daemon-reload
  fi

  GENERATED_NODE_KEY="$api_key"
}

start_daemon() {
  log "Запуск prod daemon..."
  ADMINPANELAZ_MODE=prod "$ROOT_DIR/start.sh" daemon
}

start_node_agent_daemon() {
  local api_key="${1:-}"
  if [[ -n "$api_key" ]]; then
    export NODE_AGENT_API_KEY="$api_key"
  fi
  log "Запуск node agent daemon..."
  NODE_AGENT_MODE=prod "$ROOT_DIR/start_node_agent.sh" daemon
}

print_post_install() {
  local backend_port="${BACKEND_PORT:-8000}"
  local node_port="${NODE_AGENT_PORT:-9100}"
  local node_key="${1:-}"

  cat <<EOF

================================================================================
  AdminPanelAZ — установка завершена
================================================================================

Каталог проекта:  $ROOT_DIR

Учётные данные по умолчанию:
  Логин:  admin
  Пароль: admin
  (смените при первом входе: Настройки → Смена пароля)

URL (prod / systemd):
  UI + API:  http://127.0.0.1:${backend_port}/
  API docs:  http://127.0.0.1:${backend_port}/docs

URL (dev режим ./start.sh без daemon):
  API:       http://127.0.0.1:${backend_port}/
  UI (Vite): http://127.0.0.1:5173/

Конфигурация:     $ENV_FILE
Логи (локально):  ${ADMINPANELAZ_STATE_DIR:-$ROOT_DIR/.runtime}/logs/
Логи (systemd):   /var/lib/adminpanelaz/logs/

Управление controller:
  ./start.sh              # dev, foreground
  ./start.sh daemon       # prod daemon + watchdog
  ./start.sh stop         # остановка
  ./start.sh status       # статус
  systemctl start adminpanelaz    # если установлен systemd
  systemctl status adminpanelaz

Права root:
  Backend и node agent требуют root для client.sh, doall.sh, wg, systemctl.
  systemd unit-файлы по умолчанию запускают сервисы от root.

Node agent (удалённый VPN-сервер):
  1. Скопируйте проект или backend/ на VPN-сервер
  2. sudo ./install.sh --with-node-agent [--with-systemd]
  3. Задайте API-ключ:
     export NODE_AGENT_API_KEY="ваш-секретный-ключ"
  4. ./start_node_agent.sh daemon
  5. В панели: Узлы → Добавить узел (хост, порт ${node_port}, тот же ключ)

EOF

  if [[ -n "$node_key" ]]; then
    cat <<EOF
Сгенерированный NODE_AGENT_API_KEY (сохраните!):
  $node_key

EOF
  fi

  if [[ "$WITH_SYSTEMD" == true ]]; then
    echo "Systemd: systemctl start adminpanelaz"
    if [[ "$WITH_NODE_AGENT" == true ]]; then
      echo "         systemctl start adminpanelaz-node"
    fi
    echo
  elif [[ "$WITH_DAEMON" == true ]]; then
    echo "Daemon запущен. Проверка: $ROOT_DIR/start.sh status"
    echo
  else
    cat <<EOF
Следующий шаг:
  cd $ROOT_DIR
  sudo ./start.sh daemon          # prod
  # или
  sudo ./install.sh --with-systemd

EOF
  fi
}

main() {
  parse_args "$@"
  require_root "$@"
  check_os
  resolve_project_dir
  check_antizapret
  install_system_deps
  ensure_executable_scripts
  setup_env
  setup_backend
  setup_frontend
  setup_runtime_dirs

  log "Примечание: backend запускается с правами root для интеграции с AntiZapret (client.sh, wg, systemctl)."

  if [[ "$WITH_SYSTEMD" == true ]]; then
    setup_systemd
    systemctl start adminpanelaz 2>/dev/null || warn "Не удалось запустить adminpanelaz (проверьте: systemctl status adminpanelaz)"
  elif [[ "$WITH_DAEMON" == true ]]; then
    start_daemon
  fi

  if [[ "$WITH_NODE_AGENT" == true ]]; then
    if [[ "$WITH_SYSTEMD" == true ]]; then
      setup_node_agent_systemd
      systemctl start adminpanelaz-node 2>/dev/null || warn "Не удалось запустить adminpanelaz-node (задайте NODE_AGENT_API_KEY в unit-файле)"
    else
      GENERATED_NODE_KEY="$(random_hex)"
      export NODE_AGENT_API_KEY="$GENERATED_NODE_KEY"
      start_node_agent_daemon "$GENERATED_NODE_KEY"
    fi
  fi

  print_post_install "$GENERATED_NODE_KEY"
}

main "$@"
