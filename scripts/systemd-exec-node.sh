#!/usr/bin/env bash
# Прямой запуск uvicorn node agent для systemd (adminpanelaz-node.service).
# Env уже загружен unit’ом (EnvironmentFile=node_agent.env); mTLS и exec — в systemd-exec-agent.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/systemd-exec-agent.sh
source "$ROOT_DIR/scripts/systemd-exec-agent.sh"

systemd_exec_agent node node_agent.main:app NODE_AGENT \
  "${NODE_AGENT_HOST:-0.0.0.0}" "${NODE_AGENT_PORT:-9100}" strict \
  "ANTIZAPRET_PATH=${ANTIZAPRET_PATH:-/root/antizapret}"
