#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"

# Каталог состояния: логи и PID-файлы вне корня проекта (по умолчанию скрытый .runtime/)
resolve_state_dir() {
  if [[ -n "${ADMINPANELAZ_STATE_DIR:-}" ]]; then
    echo "$ADMINPANELAZ_STATE_DIR"
    return
  fi
  echo "$ROOT_DIR/.runtime"
}

STATE_DIR="$(resolve_state_dir)"
LOG_DIR="$STATE_DIR/logs"
RUN_DIR="$STATE_DIR/run"

WATCHDOG_PID_FILE="$RUN_DIR/watchdog.pid"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
MODE_FILE="$RUN_DIR/mode"
LEGACY_PID_FILE="$ROOT_DIR/.start.sh.pids"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-127.0.0.1,::1}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
ADMINPANELAZ_MODE="${ADMINPANELAZ_MODE:-dev}"
WATCHDOG_INTERVAL="${WATCHDOG_INTERVAL:-5}"

mkdir -p "$LOG_DIR" "$RUN_DIR"

log() {
  echo "[start.sh] $*"
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

port_listener_pids() {
  local port="$1"
  ss -H -tlnp "sport = :${port}" 2>/dev/null \
    | grep -oE 'pid=[0-9]+' \
    | cut -d= -f2 \
    | sort -u
}

clear_stale_backend_listener() {
  local expected_pid listener_pid
  expected_pid="$(read_pid "$BACKEND_PID_FILE")"

  while read -r listener_pid; do
    [[ -z "$listener_pid" ]] && continue
    if [[ "$listener_pid" == "$expected_pid" ]] && is_running "$expected_pid"; then
      continue
    fi
    log_watchdog "Port $BACKEND_PORT held by stale backend PID $listener_pid; stopping"
    stop_process_tree "$listener_pid" "stale backend"
  done < <(port_listener_pids "$BACKEND_PORT")
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-60}"

  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  log "Timed out waiting for $label at $url"
  return 1
}

stop_process_tree() {
  local pid="$1"
  local name="$2"

  if ! is_running "$pid"; then
    return 0
  fi

  log "Stopping $name (PID $pid)..."
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

stop_child_services() {
  local backend_pid frontend_pid

  backend_pid="$(read_pid "$BACKEND_PID_FILE")"
  frontend_pid="$(read_pid "$FRONTEND_PID_FILE")"

  stop_process_tree "$backend_pid" "backend"
  stop_process_tree "$frontend_pid" "frontend"

  rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"
}

stop_legacy_services() {
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
    log "Stopping watchdog (PID $watchdog_pid)..."
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

  stop_child_services
  stop_legacy_services

  rm -f "$WATCHDOG_PID_FILE" "$MODE_FILE"
  log "Stopped."
}

setup_backend() {
  if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
  fi

  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  log "Installing backend dependencies..."
  pip install -q -r "$BACKEND_DIR/requirements.txt"
  mkdir -p "$BACKEND_DIR/data"

  if [[ -f "$BACKEND_DIR/.env" ]]; then
    log "Using backend/.env"
  elif [[ -f "$BACKEND_DIR/.env.example" ]]; then
    log "Tip: copy backend/.env.example to backend/.env to customize settings"
  fi
}

setup_frontend() {
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    log "Installing frontend dependencies..."
    (cd "$FRONTEND_DIR" && npm install)
  fi
}

build_frontend() {
  log "Building frontend for production..."
  (cd "$FRONTEND_DIR" && npm run build:all) >>"$LOG_DIR/frontend-build.log" 2>&1
}

launch_backend() {
  local detach="$1"
  local reload_flag=""
  local workers_flag=""

  if [[ "$ADMINPANELAZ_MODE" == "dev" ]]; then
    reload_flag="--reload"
  elif [[ "$UVICORN_WORKERS" -gt 1 ]]; then
    workers_flag="--workers $UVICORN_WORKERS"
  fi

  if [[ "$detach" == "true" ]]; then
    (
      cd "$BACKEND_DIR"
      # shellcheck source=/dev/null
      source "$VENV_DIR/bin/activate"
      if [[ "$ADMINPANELAZ_MODE" == "prod" ]]; then
        export SERVE_FRONTEND=true
        export FRONTEND_DIST_PATH="$FRONTEND_DIR/dist"
      fi
      # shellcheck disable=SC2086
      exec uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
        --proxy-headers --forwarded-allow-ips="$FORWARDED_ALLOW_IPS" $reload_flag $workers_flag
    ) >>"$LOG_DIR/backend.log" 2>&1 &
    echo "$!" >"$BACKEND_PID_FILE"
    return 0
  fi

  (
    cd "$BACKEND_DIR"
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    # shellcheck disable=SC2086
    exec uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
      --proxy-headers --forwarded-allow-ips="$FORWARDED_ALLOW_IPS" $reload_flag $workers_flag
  ) &
  echo "$! backend" >>"$LEGACY_PID_FILE"
}

launch_frontend() {
  local detach="$1"

  if [[ "$ADMINPANELAZ_MODE" == "prod" ]]; then
    return 0
  fi

  if [[ "$detach" == "true" ]]; then
    (
      cd "$FRONTEND_DIR"
      exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
    ) >>"$LOG_DIR/frontend.log" 2>&1 &
    echo "$!" >"$FRONTEND_PID_FILE"
    return 0
  fi

  (
    cd "$FRONTEND_DIR"
    exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
  ) &
  echo "$! frontend" >>"$LEGACY_PID_FILE"
}

ensure_backend_running() {
  local backend_pid
  backend_pid="$(read_pid "$BACKEND_PID_FILE")"

  if is_running "$backend_pid"; then
    return 0
  fi

  clear_stale_backend_listener
  log_watchdog "Backend not running; restarting..."
  launch_backend true
}

ensure_frontend_running() {
  local frontend_pid

  if [[ "$ADMINPANELAZ_MODE" == "prod" ]]; then
    return 0
  fi

  frontend_pid="$(read_pid "$FRONTEND_PID_FILE")"
  if is_running "$frontend_pid"; then
    return 0
  fi

  log_watchdog "Frontend not running; restarting..."
  launch_frontend true
}

watchdog_loop() {
  trap 'log_watchdog "Received stop signal"; stop_child_services; exit 0' TERM INT

  log_watchdog "Watchdog started (mode=$ADMINPANELAZ_MODE)"

  clear_stale_backend_listener
  setup_backend
  setup_frontend
  if [[ "$ADMINPANELAZ_MODE" == "prod" ]]; then
    build_frontend
  fi

  launch_backend true
  launch_frontend true

  while true; do
    ensure_backend_running
    ensure_frontend_running
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
    log "Daemon already running (PID $(read_pid "$WATCHDOG_PID_FILE")). Run './start.sh stop' first."
    exit 1
  fi

  echo "$ADMINPANELAZ_MODE" >"$MODE_FILE"

  log "Starting daemon (mode=$ADMINPANELAZ_MODE)..."
  nohup env ADMINPANELAZ_MODE="$ADMINPANELAZ_MODE" "$0" __watchdog__ \
    >>"$LOG_DIR/watchdog.log" 2>&1 &
  local watchdog_pid=$!
  echo "$watchdog_pid" >"$WATCHDOG_PID_FILE"
  disown "$watchdog_pid" 2>/dev/null || true

  wait_for_url "http://127.0.0.1:${BACKEND_PORT}/api/health" "backend"

  if [[ "$ADMINPANELAZ_MODE" == "dev" ]]; then
    wait_for_url "http://${FRONTEND_HOST}:${FRONTEND_PORT}/" "frontend"
  else
    wait_for_url "http://127.0.0.1:${BACKEND_PORT}/" "frontend (static)"
  fi

  echo ""
  log "Daemon running (watchdog PID $watchdog_pid):"
  echo "  Mode:     $ADMINPANELAZ_MODE"
  echo "  API:      http://127.0.0.1:${BACKEND_PORT}"
  echo "  Docs:     http://127.0.0.1:${BACKEND_PORT}/docs"
  if [[ "$ADMINPANELAZ_MODE" == "prod" ]]; then
    echo "  UI:       http://127.0.0.1:${BACKEND_PORT}/"
  else
    echo "  UI:       http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  fi
  echo "  Logs:     $LOG_DIR/"
  echo "  PIDs:     $RUN_DIR/"
  echo ""
  log "Use './start.sh status' or './start.sh stop'."
}

show_status() {
  local watchdog_pid backend_pid frontend_pid mode

  watchdog_pid="$(read_pid "$WATCHDOG_PID_FILE")"
  backend_pid="$(read_pid "$BACKEND_PID_FILE")"
  frontend_pid="$(read_pid "$FRONTEND_PID_FILE")"
  mode="$(cat "$MODE_FILE" 2>/dev/null || echo "n/a")"

  echo "AdminPanelAZ status"
  echo "  Mode:      $mode"

  if is_running "$watchdog_pid"; then
    echo "  Watchdog:  running (PID $watchdog_pid)"
  else
    echo "  Watchdog:  stopped"
  fi

  if is_running "$backend_pid"; then
    echo "  Backend:   running (PID $backend_pid, port $BACKEND_PORT)"
  else
    echo "  Backend:   stopped"
  fi

  if [[ "$mode" == "prod" ]]; then
    echo "  Frontend:  served via backend (static dist/)"
  elif is_running "$frontend_pid"; then
    echo "  Frontend:  running (PID $frontend_pid, port $FRONTEND_PORT)"
  else
    echo "  Frontend:  stopped"
  fi

  echo "  Logs:      $LOG_DIR/"
  echo "  PID files: $RUN_DIR/"
}

restart_daemon() {
  local mode="$ADMINPANELAZ_MODE"

  if [[ -f "$MODE_FILE" ]]; then
    mode="$(cat "$MODE_FILE")"
  fi

  stop_services
  ADMINPANELAZ_MODE="$mode" start_daemon
}

cleanup_foreground() {
  log "Shutting down..."
  stop_services
}

start_foreground() {
  if daemon_is_running; then
    log "Daemon is running. Use './start.sh stop' before foreground start."
    exit 1
  fi

  ADMINPANELAZ_MODE="dev"
  : >"$LEGACY_PID_FILE"
  trap cleanup_foreground INT TERM

  setup_backend
  setup_frontend

  log "Starting backend (uvicorn, dev mode)..."
  launch_backend false

  log "Starting frontend (Vite dev server)..."
  launch_frontend false

  wait_for_url "http://127.0.0.1:${BACKEND_PORT}/api/health" "backend"
  wait_for_url "http://${FRONTEND_HOST}:${FRONTEND_PORT}/" "frontend"

  echo ""
  log "Ready (foreground dev mode):"
  echo "  API:  http://127.0.0.1:${BACKEND_PORT}"
  echo "  Docs: http://127.0.0.1:${BACKEND_PORT}/docs"
  echo "  UI:   http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  echo ""
  log "Press Ctrl+C to stop both services."

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
  start              Foreground dev mode (backend + Vite, Ctrl+C to stop) [default]
  daemon [dev|prod]  Detached daemon with watchdog (default: prod)
  stop               Gracefully stop daemon or foreground services
  status             Show running processes and log locations
  restart            Restart daemon (preserves last daemon mode)
  watchdog           Internal: run watchdog loop in foreground (for systemd)

Environment:
  ADMINPANELAZ_STATE_DIR  runtime dir for logs/PIDs (default: $ROOT_DIR/.runtime)
  ADMINPANELAZ_MODE       dev | prod (prod serves frontend/dist via backend)
  BACKEND_HOST            default: 127.0.0.1 (localhost; за Nginx — только 127.0.0.1)
  BACKEND_PORT            default: 8000
  UVICORN_WORKERS         prod workers (default: 1; >1 — см. AUTH_RATE_LIMIT_BACKEND=redis)
  FORWARDED_ALLOW_IPS     trusted proxies for X-Forwarded-* (default: 127.0.0.1,::1)
  FRONTEND_HOST           default: 127.0.0.1 (dev daemon/foreground)
  FRONTEND_PORT           default: 5173 (dev only)
  WATCHDOG_INTERVAL       seconds between health checks (default: 5)

State: $STATE_DIR/
Logs:  $LOG_DIR/
PIDs:   $RUN_DIR/
EOF
}

parse_daemon_args() {
  ADMINPANELAZ_MODE="prod"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      dev | prod)
        ADMINPANELAZ_MODE="$1"
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
    echo "$ADMINPANELAZ_MODE" >"$MODE_FILE"
    watchdog_loop
    ;;
  __watchdog__)
    if [[ -f "$MODE_FILE" ]]; then
      ADMINPANELAZ_MODE="$(cat "$MODE_FILE")"
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
