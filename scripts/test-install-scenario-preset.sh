#!/usr/bin/env bash
# scripts/test-install-scenario-preset.sh
# Stage 5 §8.2: install/wizard apply scenario presets.
# Non-interactive panel-only → panel_only; wizard asks home/commercial (default home); legacy env rejected.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

extract() {
  local file="$1" fn
  shift
  for fn in "$@"; do
    sed -n "/^${fn}() {/,/^}/p" "$file"
  done
}

fail() { echo "  FAIL $*" >&2; exit 1; }

# Stub python apply: records args into the target .env
write_stub_tree() {
  mkdir -p "$TMP_DIR/scripts" "$TMP_DIR/backend"
  cat >"$TMP_DIR/scripts/apply-scenario-preset.py" <<'PY'
import sys
from pathlib import Path
Path(sys.argv[sys.argv.index("--env")+1]).write_text(
    f"SCENARIO_PRESET={sys.argv[1]}\n", encoding="utf-8"
)
print(f"Applied scenario: {sys.argv[1]}")
PY
  : >"$TMP_DIR/backend/.env"
}

echo "[test] apply_wiz_scenario_preset writes panel_only via script"
write_stub_tree
ENV_FILE="$TMP_DIR/backend/.env" ROOT_DIR="$TMP_DIR" BACKEND_DIR="$TMP_DIR/backend" bash -c '
  set -euo pipefail
  log() { :; }
  die() { echo "DIE $*"; exit 1; }
  ap_require_python() { echo python3; }
  eval "$1"
  apply_wiz_scenario_preset panel_only
' bash "$(extract "$ROOT_DIR/install.sh" apply_wiz_scenario_preset)"
grep -qx "SCENARIO_PRESET=panel_only" "$TMP_DIR/backend/.env" || fail "panel_only not applied"
echo "  OK"

echo "[test] wizard asks home/commercial; -y ставит домашний сценарий"
WIZ="$(extract "$ROOT_DIR/scripts/install-wizard.sh" wiz_prompt_choice wizard_ask_scenario_preset)"
run_scenario() {
  local accept="$1" preset="$2" input="${3:-}"
  ACCEPT="$accept" PRESET="$preset" bash -c '
    set -euo pipefail
    wiz_step() { :; }
    ui_info_box() { :; }
    print_info() { :; }
    WIZ_INSTALL_TYPE=controller
    WIZ_ACCEPT_DEFAULTS="$ACCEPT"
    WIZ_SCENARIO_PRESET="$PRESET"
    eval "$1"
    wizard_ask_scenario_preset
    echo "RESULT $WIZ_SCENARIO_PRESET"
  ' bash "$WIZ" <<<"$input" | tail -1
}

[[ "$(run_scenario true "")" == "RESULT home" ]] || fail "дефолт: $(run_scenario true "")"
echo "  OK"

echo "[test] интерактивно: ответ 2 — коммерческий, Enter — домашний"
[[ "$(run_scenario false "" 2)" == "RESULT commercial" ]] || fail "ответ 2: $(run_scenario false "" 2)"
[[ "$(run_scenario false "" "")" == "RESULT home" ]] || fail "Enter: $(run_scenario false "" "")"
echo "  OK"

echo "[test] WIZ_SCENARIO_PRESET из env: commercial — вариант по умолчанию, panel_only — без вопроса"
[[ "$(run_scenario true commercial)" == "RESULT commercial" ]] || fail "env commercial"
[[ "$(run_scenario true panel_only)" == "RESULT panel_only" ]] || fail "env panel_only"
echo "  OK"

echo "[test] install.sh still references apply-scenario-preset.py (not resource-profile)"
grep -q 'apply-scenario-preset.py' "$ROOT_DIR/install.sh" || fail "missing new script ref"
grep -q 'apply-resource-profile.py' "$ROOT_DIR/install.sh" && fail "old script still referenced" || true
echo "  OK"

echo "[test] non-interactive path documents panel_only (source grep)"
grep -n 'panel_only' "$ROOT_DIR/install.sh" | head -5
grep -q 'apply_wiz_scenario_preset "panel_only"' "$ROOT_DIR/install.sh" \
  || grep -q "panel_only" "$ROOT_DIR/install.sh" \
  || fail "non-interactive panel_only missing"
echo "  OK"

echo "[test] legacy profile names are rejected (no WIZ_RESOURCE_PROFILE / minimal|standard|full presets)"
grep -q 'WIZ_RESOURCE_PROFILE' "$ROOT_DIR/install.sh" && fail "install.sh still uses WIZ_RESOURCE_PROFILE" || true
grep -q 'WIZ_RESOURCE_PROFILE' "$ROOT_DIR/scripts/install-wizard.sh" \
  && fail "install-wizard.sh still uses WIZ_RESOURCE_PROFILE" || true
grep -q 'apply_wiz_resource_profile' "$ROOT_DIR/install.sh" && fail "old helper still present" || true
grep -q 'wizard_ask_resource_profile' "$ROOT_DIR/scripts/install-wizard.sh" \
  && fail "old wizard helper still present" || true
[[ -f "$ROOT_DIR/scripts/apply-resource-profile.py" ]] \
  && fail "scripts/apply-resource-profile.py must be deleted" || true
echo "  OK"

echo "[test] wizard summary shows the scenario row"
grep -q 'ui_summary_row "Сценарий" "$scenario_label ($WIZ_SCENARIO_PRESET)"' "$ROOT_DIR/scripts/install-wizard.sh" \
  || fail "wizard summary row for scenario missing"
echo "  OK"

echo "All install scenario preset tests passed."
