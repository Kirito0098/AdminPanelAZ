#!/bin/bash
# Диагностика запуска AdminPanelAZ — CLI + цветной вывод.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIAGNOSTICS_CLI="$ROOT_DIR/scripts/site-diagnostics-cli.py"
INSTALL_DIR="${INSTALL_DIR:-$ROOT_DIR}"
SERVICE_NAME="${SERVICE_NAME:-adminpanelaz}"
VENV_PATH="${VENV_PATH:-$ROOT_DIR/backend/.venv}"

GREEN=$(printf '\033[0;32m')
YELLOW=$(printf '\033[1;33m')
RED=$(printf '\033[0;31m')
CYAN=$(printf '\033[0;36m')
NC=$(printf '\033[0m')

ui_ok() { printf "  ${GREEN}✓${NC}  %s\n" "$*"; }
ui_warn() { printf "  ${YELLOW}!${NC}  %s\n" "$*" >&2; }
ui_fail() { printf "  ${RED}✗${NC}  %s\n" "$*" >&2; }
ui_info() { printf "  ${CYAN}i${NC}  %s\n" "$*"; }
ui_section() { printf "\n${CYAN}── %s ──${NC}\n" "$*"; }

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

_site_diagnostics_print_colored() {
    local line
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
        "[OK]"*)
            ui_ok "${line#\[OK\] }"
            ;;
        "[WARN]"*)
            ui_warn "${line#\[WARN\] }"
            ;;
        "[FAIL]"*)
            ui_fail "${line#\[FAIL\] }"
            ;;
        "       "*)
            printf "         %s\n" "${line#       }"
            ;;
        "Рекомендуемые команды:"*)
            ui_section "$line"
            ;;
        "  "*)
            ui_info "${line#  }"
            ;;
        "")
            printf "\n"
            ;;
        *)
            printf "  %s\n" "$line"
            ;;
        esac
    done
}

diagnose_site_startup() {
    _site_diagnostics_check || return 1
    ui_section "Диагностика запуска AdminPanelAZ"
    ui_info "Каталог: $INSTALL_DIR | сервис: $SERVICE_NAME"
    printf "\n"

    local tmp code
    tmp=$(mktemp)
    _site_diagnostics_invoke run >"$tmp"
    code=$?
    _site_diagnostics_print_colored <"$tmp"
    rm -f "$tmp"
    printf "\n"
    if [ "$code" -eq 0 ]; then
        ui_ok "Критических проблем не обнаружено"
    else
        ui_fail "Есть ошибки (код выхода: $code). См. подсказки выше."
    fi
    return "$code"
}

run_site_diagnostics_cli() {
    _site_diagnostics_check || return 1
    _site_diagnostics_invoke run
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    run_site_diagnostics_cli
    exit $?
fi
