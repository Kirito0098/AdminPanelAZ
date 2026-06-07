#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
PID_FILE="$ROOT_DIR/.start.sh.pids"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

log() {
  echo "[start.sh] $*"
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

stop_services() {
  if [[ ! -f "$PID_FILE" ]]; then
    log "No running services found."
    return 0
  fi

  while read -r pid name; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      log "Stopping $name (PID $pid)..."
      kill "$pid" 2>/dev/null || true
      pkill -P "$pid" 2>/dev/null || true
    fi
  done <"$PID_FILE"

  rm -f "$PID_FILE"
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

cleanup() {
  log "Shutting down..."
  stop_services
}

start_services() {
  if [[ -f "$PID_FILE" ]]; then
    log "Services may already be running. Run './start.sh stop' first."
    exit 1
  fi

  : >"$PID_FILE"
  trap cleanup INT TERM

  setup_backend
  setup_frontend

  log "Starting backend (uvicorn)..."
  (
    cd "$BACKEND_DIR"
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    exec uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload
  ) &
  backend_pid=$!
  echo "$backend_pid backend" >>"$PID_FILE"

  log "Starting frontend (Vite)..."
  (
    cd "$FRONTEND_DIR"
    exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
  ) &
  frontend_pid=$!
  echo "$frontend_pid frontend" >>"$PID_FILE"

  wait_for_url "http://127.0.0.1:${BACKEND_PORT}/api/health" "backend"
  wait_for_url "http://${FRONTEND_HOST}:${FRONTEND_PORT}/" "frontend"

  echo ""
  log "Ready:"
  echo "  API:  http://127.0.0.1:${BACKEND_PORT}"
  echo "  Docs: http://127.0.0.1:${BACKEND_PORT}/docs"
  echo "  UI:   http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  echo ""
  log "Press Ctrl+C to stop both services."

  wait "$backend_pid" "$frontend_pid"
}

case "${1:-start}" in
  start)
    start_services
    ;;
  stop)
    stop_services
    ;;
  *)
    echo "Usage: $0 [start|stop]"
    exit 1
    ;;
esac
