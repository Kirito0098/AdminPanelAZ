#!/bin/bash
# Диагностика запуска AdminPanelAZ — CLI + цветной вывод.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIAGNOSTICS_CLI="$ROOT_DIR/scripts/site-diagnostics-cli.py"
INSTALL_DIR="${INSTALL_DIR:-$ROOT_DIR}"
SERVICE_NAME="${SERVICE_NAME:-adminpanelaz}"
VENV_PATH="${VENV_PATH:-$ROOT_DIR/backend/.venv}"

RED=$(printf '\033[0;31m')
NC=$(printf '\033[0m')

ui_fail() { printf "  ${RED}✗${NC}  %s\n" "$*" >&2; }

_site_diagnostics_python() {
    if [ -x "$VENV_PATH/bin/python" ]; then
        printf '%s\n' "$VENV_PATH/bin/python"
        return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return 0
    fi
    return 1
}

_site_diagnostics_check() {
    local py
    if [ ! -f "$SITE_DIAGNOSTICS_CLI" ]; then
        ui_fail "Не найден CLI: $SITE_DIAGNOSTICS_CLI"
        return 1
    fi
    py=$(_site_diagnostics_python) || {
        ui_fail "Python не найден (нужен backend/.venv или python3)"
        return 1
    }
    return 0
}

_site_diagnostics_invoke() {
    local py
    py=$(_site_diagnostics_python) || return 1
    INSTALL_DIR="$INSTALL_DIR" SERVICE_NAME="$SERVICE_NAME" VENV_PATH="$VENV_PATH" \
        "$py" "$SITE_DIAGNOSTICS_CLI" "$@"
}


run_site_diagnostics_cli() {
    _site_diagnostics_check || return 1
    _site_diagnostics_invoke run
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_site_diagnostics_cli
    exit $?
fi
