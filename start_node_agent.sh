#!/usr/bin/env bash
# Compat shim for pre-2.19 systemd units: ExecStart=…/start_node_agent.sh watchdog prod
# New installs use scripts/systemd-exec-node.sh. Node update / startup refreshes the unit.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
  stop)
    exit 0
    ;;
  *)
    echo "[start_node_agent.sh] compat → systemd-exec-node.sh (unit will be refreshed on update/startup)" >&2
    exec "$ROOT_DIR/scripts/systemd-exec-node.sh"
    ;;
esac
