#!/usr/bin/env bash
# scripts/test-install-scenario-preset.sh
# Stage 5 §8.2: install/wizard apply scenario presets.
# Non-interactive panel-only → panel_only; wizard default commercial; legacy env var name rejected.
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

echo "[test] wizard default WIZ_SCENARIO_PRESET is commercial"
WIZ="$(extract "$ROOT_DIR/scripts/install-wizard.sh" wizard_ask_scenario_preset)"
out="$(WIZ_INSTALL_TYPE=controller bash -c '
  set -euo pipefail
  eval "$1"
  wizard_ask_scenario_preset
  echo "$WIZ_SCENARIO_PRESET"
' bash "$WIZ")"
[[ "$out" == "commercial" ]] || fail "wizard default: $out"
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
grep -q 'ui_summary_row "Сценарий" "$WIZ_SCENARIO_PRESET"' "$ROOT_DIR/scripts/install-wizard.sh" \
  || fail "wizard summary row for scenario missing"
echo "  OK"

echo "All install scenario preset tests passed."
