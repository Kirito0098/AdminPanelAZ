#!/usr/bin/env bash
# Прямой запуск uvicorn proxy agent для systemd (adminpanelaz-proxy.service).
# Env уже загружен unit’ом (EnvironmentFile=proxy_agent.env); mTLS и exec — в systemd-exec-agent.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/systemd-exec-agent.sh
source "$ROOT_DIR/scripts/systemd-exec-agent.sh"

systemd_exec_agent proxy proxy_agent.main:app PROXY_AGENT \
  "${PROXY_AGENT_HOST:-0.0.0.0}" "${PROXY_AGENT_PORT:-9101}" lenient
