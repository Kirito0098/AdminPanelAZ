#!/usr/bin/env bash
# Compat shim for pre-2.19 systemd units: ExecStart=…/start.sh watchdog prod
# New installs use scripts/systemd-exec-panel.sh. UI/CLI update refreshes units.
# Without this file, «Обновить» на старом unit’е падает после удаления полного start.sh.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
  stop)
    # ExecStop from legacy units — main process is killed by systemd after this.
    exit 0
    ;;
  *)
    echo "[start.sh] compat → systemd-exec-panel.sh (unit will be refreshed on update/startup)" >&2
    exec "$ROOT_DIR/scripts/systemd-exec-panel.sh"
    ;;
esac
