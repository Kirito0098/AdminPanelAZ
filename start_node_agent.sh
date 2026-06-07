#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"

export NODE_AGENT_API_KEY="${NODE_AGENT_API_KEY:-change-me-node-agent-key}"
export ANTIZAPRET_PATH="${ANTIZAPRET_PATH:-/root/antizapret}"
export NODE_AGENT_PORT="${NODE_AGENT_PORT:-9100}"

if [[ ! -d "$VENV" ]]; then
  echo "Создание venv..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$BACKEND/requirements.txt"
fi

cd "$BACKEND"
export PYTHONPATH="$BACKEND:${PYTHONPATH:-}"
exec "$VENV/bin/uvicorn" node_agent.main:app --host 0.0.0.0 --port "$NODE_AGENT_PORT"
