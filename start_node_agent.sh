#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"
NODE_ENV_FILE="${NODE_AGENT_ENV_FILE:-$BACKEND_DIR/node_agent.env}"

if [[ -f "$NODE_ENV_FILE" && -z "${NODE_AGENT_ENV_LOADED:-}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$NODE_ENV_FILE"
  set +a
  export NODE_AGENT_ENV_LOADED=1
fi

# Каталог состояния node agent (логи и PID вне корня проекта)
resolve_state_dir() {
  if [[ -n "${NODE_AGENT_STATE_DIR:-}" ]]; then
    echo "$NODE_AGENT_STATE_DIR"
    return
  fi
  echo "$ROOT_DIR/.runtime/node"
}

STATE_DIR="$(resolve_state_dir)"
LOG_DIR="$STATE_DIR/logs"
RUN_DIR="$STATE_DIR/run"

WATCHDOG_PID_FILE="$RUN_DIR/watchdog.pid"
AGENT_PID_FILE="$RUN_DIR/agent.pid"
MODE_FILE="$RUN_DIR/mode"
LEGACY_PID_FILE="$STATE_DIR/.start_node_agent.pids"

NODE_AGENT_API_KEY="${NODE_AGENT_API_KEY:-change-me-node-agent-key}"
ANTIZAPRET_PATH="${ANTIZAPRET_PATH:-/root/antizapret}"
NODE_AGENT_HOST="${NODE_AGENT_HOST:-0.0.0.0}"
NODE_AGENT_PORT="${NODE_AGENT_PORT:-9100}"
NODE_AGENT_MODE="${NODE_AGENT_MODE:-prod}"
WATCHDOG_INTERVAL="${WATCHDOG_INTERVAL:-5}"

mkdir -p "$LOG_DIR" "$RUN_DIR"

log() {
  echo "[start_node_agent.sh] $*"
}

log_watchdog() {
  echo "[watchdog $(date '+%Y-%m-%d %H:%M:%S')] $*" >>"$LOG_DIR/watchdog.log"
}

is_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
  local file="$1"
  if [[ -f "$file" ]]; then
    tr -d '[:space:]' <"$file"
  fi
}

wait_for_health() {
  local attempts="${1:-60}"

  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS -H "X-Node-Key: $NODE_AGENT_API_KEY" \
      "http://127.0.0.1:${NODE_AGENT_PORT}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  log "Таймаут ожидания node agent на порту $NODE_AGENT_PORT"
  return 1
}

stop_process_tree() {
  local pid="$1"
  local name="$2"

  if ! is_running "$pid"; then
    return 0
  fi

  log "Остановка $name (PID $pid)..."
  kill -TERM "$pid" 2>/dev/null || true

  local i
  for ((i = 0; i < 10; i++)); do
    is_running "$pid" || break
    sleep 1
  done

  if is_running "$pid"; then
    kill -KILL "$pid" 2>/dev/null || true
  fi
  pkill -TERM -P "$pid" 2>/dev/null || true
  sleep 1
  pkill -KILL -P "$pid" 2>/dev/null || true
}

stop_agent() {
  local agent_pid
  agent_pid="$(read_pid "$AGENT_PID_FILE")"
  stop_process_tree "$agent_pid" "node agent"
  rm -f "$AGENT_PID_FILE"
}

stop_legacy() {
  if [[ ! -f "$LEGACY_PID_FILE" ]]; then
    return 0
  fi

  while read -r pid name; do
    stop_process_tree "$pid" "$name"
  done <"$LEGACY_PID_FILE"
  rm -f "$LEGACY_PID_FILE"
}

stop_services() {
  local watchdog_pid
  watchdog_pid="$(read_pid "$WATCHDOG_PID_FILE")"

  if is_running "$watchdog_pid"; then
    log "Остановка watchdog (PID $watchdog_pid)..."
    kill -TERM "$watchdog_pid" 2>/dev/null || true

    local i
    for ((i = 0; i < 15; i++)); do
      is_running "$watchdog_pid" || break
      sleep 1
    done

    if is_running "$watchdog_pid"; then
      kill -KILL "$watchdog_pid" 2>/dev/null || true
    fi
  fi

  stop_agent
  stop_legacy

  rm -f "$WATCHDOG_PID_FILE" "$MODE_FILE"
  log "Остановлен."
}

setup_backend() {
  if [[ ! -d "$VENV_DIR" ]]; then
    log "Создание Python virtual environment..."
    python3 -m venv "$VENV_DIR"
  fi

  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  log "Установка зависимостей backend..."
  pip install -q -r "$BACKEND_DIR/requirements.txt"
}

mtls_uvicorn_flags() {
  if [[ "${NODE_AGENT_MTLS_ENABLED:-false}" != "true" ]]; then
    return
  fi
  local cert="${NODE_AGENT_MTLS_SERVER_CERT:-/etc/adminpanelaz/mtls/agent.crt}"
  local key="${NODE_AGENT_MTLS_SERVER_KEY:-/etc/adminpanelaz/mtls/agent.key}"
  local ca="${NODE_AGENT_MTLS_CA_CERT:-/etc/adminpanelaz/mtls/ca.crt}"
  if [[ -f "$cert" && -f "$key" && -f "$ca" ]]; then
    echo "--ssl-certfile $cert --ssl-keyfile $key --ssl-ca-certs $ca --ssl-cert-reqs 2"
  fi
}

launch_agent() {
  local detach="$1"
  local reload_flag=""
  local mtls_flags
  mtls_flags="$(mtls_uvicorn_flags)"

  if [[ "$NODE_AGENT_MODE" == "dev" ]]; then
    reload_flag="--reload"
  fi

  export NODE_AGENT_API_KEY ANTIZAPRET_PATH NODE_AGENT_PORT

  if [[ "$detach" == "true" ]]; then
    (
      cd "$BACKEND_DIR"
      export PYTHONPATH="$BACKEND_DIR:${PYTHONPATH:-}"
      # shellcheck source=/dev/null
      source "$VENV_DIR/bin/activate"
      # shellcheck disable=SC2086
      exec uvicorn node_agent.main:app --host "$NODE_AGENT_HOST" --port "$NODE_AGENT_PORT" $reload_flag $mtls_flags
    ) >>"$LOG_DIR/agent.log" 2>&1 &
    echo "$!" >"$AGENT_PID_FILE"
    return 0
  fi

  (
    cd "$BACKEND_DIR"
    export PYTHONPATH="$BACKEND_DIR:${PYTHONPATH:-}"
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    # shellcheck disable=SC2086
    exec uvicorn node_agent.main:app --host "$NODE_AGENT_HOST" --port "$NODE_AGENT_PORT" $reload_flag $mtls_flags
  ) &
  echo "$! node-agent" >>"$LEGACY_PID_FILE"
}

ensure_agent_running() {
  local agent_pid
  agent_pid="$(read_pid "$AGENT_PID_FILE")"

  if is_running "$agent_pid"; then
    return 0
  fi

  log_watchdog "Node agent не запущен; перезапуск..."
  launch_agent true
}

watchdog_loop() {
  trap 'log_watchdog "Получен сигнал остановки"; stop_agent; exit 0' TERM INT

  log_watchdog "Watchdog запущен (mode=$NODE_AGENT_MODE)"

  setup_backend
  launch_agent true

  while true; do
    ensure_agent_running
    sleep "$WATCHDOG_INTERVAL"
  done
}

daemon_is_running() {
  local watchdog_pid
  watchdog_pid="$(read_pid "$WATCHDOG_PID_FILE")"
  is_running "$watchdog_pid"
}

start_daemon() {
  if daemon_is_running; then
    log "Daemon уже запущен (PID $(read_pid "$WATCHDOG_PID_FILE")). Сначала: ./start_node_agent.sh stop"
    exit 1
  fi

  echo "$NODE_AGENT_MODE" >"$MODE_FILE"

  log "Запуск daemon (mode=$NODE_AGENT_MODE)..."
  nohup env \
    NODE_AGENT_MODE="$NODE_AGENT_MODE" \
    NODE_AGENT_API_KEY="$NODE_AGENT_API_KEY" \
    ANTIZAPRET_PATH="$ANTIZAPRET_PATH" \
    NODE_AGENT_HOST="$NODE_AGENT_HOST" \
    NODE_AGENT_PORT="$NODE_AGENT_PORT" \
    NODE_AGENT_STATE_DIR="$STATE_DIR" \
    "$0" __watchdog__ \
    >>"$LOG_DIR/watchdog.log" 2>&1 &
  local watchdog_pid=$!
  echo "$watchdog_pid" >"$WATCHDOG_PID_FILE"
  disown "$watchdog_pid" 2>/dev/null || true

  wait_for_health

  echo ""
  log "Daemon запущен (watchdog PID $watchdog_pid):"
  echo "  Mode:     $NODE_AGENT_MODE"
  echo "  API:      http://127.0.0.1:${NODE_AGENT_PORT}"
  echo "  Health:   http://127.0.0.1:${NODE_AGENT_PORT}/health (X-Node-Key)"
  echo "  State:    $STATE_DIR/"
  echo "  Logs:     $LOG_DIR/"
  echo "  PIDs:     $RUN_DIR/"
  echo ""
  log "Команды: ./start_node_agent.sh status | stop"
}

show_status() {
  local watchdog_pid agent_pid mode

  watchdog_pid="$(read_pid "$WATCHDOG_PID_FILE")"
  agent_pid="$(read_pid "$AGENT_PID_FILE")"
  mode="$(cat "$MODE_FILE" 2>/dev/null || echo "n/a")"

  echo "Node Agent status"
  echo "  Mode:      $mode"

  if is_running "$watchdog_pid"; then
    echo "  Watchdog:  running (PID $watchdog_pid)"
  else
    echo "  Watchdog:  stopped"
  fi

  if is_running "$agent_pid"; then
    echo "  Agent:     running (PID $agent_pid, port $NODE_AGENT_PORT)"
  else
    echo "  Agent:     stopped"
  fi

  echo "  State:     $STATE_DIR/"
  echo "  Logs:      $LOG_DIR/"
  echo "  PID files: $RUN_DIR/"
}

restart_daemon() {
  local mode="$NODE_AGENT_MODE"

  if [[ -f "$MODE_FILE" ]]; then
    mode="$(cat "$MODE_FILE")"
  fi

  stop_services
  NODE_AGENT_MODE="$mode" start_daemon
}

cleanup_foreground() {
  log "Завершение..."
  stop_services
}

start_foreground() {
  if daemon_is_running; then
    log "Daemon запущен. Сначала: ./start_node_agent.sh stop"
    exit 1
  fi

  NODE_AGENT_MODE="dev"
  : >"$LEGACY_PID_FILE"
  trap cleanup_foreground INT TERM

  setup_backend

  log "Запуск node agent (uvicorn, dev mode)..."
  launch_agent false

  wait_for_health

  echo ""
  log "Готово (foreground dev mode):"
  echo "  API:    http://127.0.0.1:${NODE_AGENT_PORT}"
  echo "  Health: http://127.0.0.1:${NODE_AGENT_PORT}/health"
  echo ""
  log "Ctrl+C для остановки."

  local pids=()
  while read -r pid _; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done <"$LEGACY_PID_FILE"

  if ((${#pids[@]} > 0)); then
    wait "${pids[@]}" 2>/dev/null || true
  fi
}

usage() {
  cat <<EOF
Usage: $0 [command] [options]

Commands:
  start              Foreground dev mode (uvicorn --reload, Ctrl+C to stop) [default]
  daemon [dev|prod]  Detached daemon with watchdog (default: prod)
  stop               Gracefully stop daemon or foreground process
  status             Show running processes and log locations
  restart            Restart daemon (preserves last daemon mode)
  watchdog           Internal: run watchdog loop in foreground (for systemd)

Environment:
  NODE_AGENT_STATE_DIR  runtime dir for logs/PIDs (default: $ROOT_DIR/.runtime/node)
  NODE_AGENT_API_KEY    API key for X-Node-Key header (required in production)
  ANTIZAPRET_PATH       path to AntiZapret install (default: /root/antizapret)
  NODE_AGENT_HOST       default: 0.0.0.0
  NODE_AGENT_PORT       default: 9100
  NODE_AGENT_MODE       dev | prod (dev enables uvicorn --reload)
  WATCHDOG_INTERVAL     seconds between health checks (default: 5)

State: $STATE_DIR/
Logs:  $LOG_DIR/
PIDs:   $RUN_DIR/
EOF
}

parse_daemon_args() {
  NODE_AGENT_MODE="prod"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      dev | prod)
        NODE_AGENT_MODE="$1"
        shift
        ;;
      *)
        echo "Unknown daemon option: $1"
        usage
        exit 1
        ;;
    esac
  done
}

case "${1:-start}" in
  start)
    start_foreground
    ;;
  daemon)
    shift
    parse_daemon_args "$@"
    start_daemon
    ;;
  stop)
    stop_services
    ;;
  status)
    show_status
    ;;
  restart)
    restart_daemon
    ;;
  watchdog)
    shift
    parse_daemon_args "$@"
    echo "$NODE_AGENT_MODE" >"$MODE_FILE"
    watchdog_loop
    ;;
  __watchdog__)
    if [[ -f "$MODE_FILE" ]]; then
      NODE_AGENT_MODE="$(cat "$MODE_FILE")"
    fi
    watchdog_loop
    ;;
  -h | --help | help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
