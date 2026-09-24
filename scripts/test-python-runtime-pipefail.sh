#!/usr/bin/env bash
# Проверка source python-runtime.sh с pipefail, как в install.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Делаем каждого кандидата длиннее буфера канала, чтобы раннее закрытие
# читающей команды гарантированно вызывало SIGPIPE у записывающей.
long_major="$(printf '%080000d' 0)"
ADMINPANELAZ_PYTHON_MAJOR="$long_major" bash -c '
  set -euo pipefail
  source "$1"
  [[ "$ADMINPANELAZ_PYTHON_VERSION" == "$ADMINPANELAZ_PYTHON_MAJOR".* ]]
' bash "$ROOT_DIR/scripts/python-runtime.sh"

echo "[test] python-runtime.sh загружается при включённом pipefail"
