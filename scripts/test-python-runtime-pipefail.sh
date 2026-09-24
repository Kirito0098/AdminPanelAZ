#!/usr/bin/env bash
# Sourcing python-runtime.sh must succeed with pipefail enabled, as in install.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Make each candidate longer than a pipe buffer so an early-exiting consumer
# reliably triggers SIGPIPE in the producer.
long_major="$(printf '%080000d' 0)"
ADMINPANELAZ_PYTHON_MAJOR="$long_major" bash -c '
  set -euo pipefail
  source "$1"
  [[ "$ADMINPANELAZ_PYTHON_VERSION" == "$ADMINPANELAZ_PYTHON_MAJOR".* ]]
' bash "$ROOT_DIR/scripts/python-runtime.sh"

echo "[test] python-runtime.sh loads with pipefail enabled"
