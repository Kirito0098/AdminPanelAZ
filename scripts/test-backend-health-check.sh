#!/usr/bin/env bash
# Быстрые тесты логики backend-health-check.sh (без запущенного backend).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/backend-health-check.sh
source "$ROOT_DIR/scripts/backend-health-check.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

assert_eq() {
  local got="$1" want="$2" label="$3"
  if [[ "$got" == "$want" ]]; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label (got='$got' want='$want')" >&2
  fi
}

assert_urls_contain() {
  local urls="$1" needle="$2" label="$3"
  if printf '%s\n' "$urls" | grep -qF "$needle"; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label (missing '$needle' in:$urls)" >&2
  fi
}

echo "[test] uvicorn_selfsigned via wizard"
BHC_ENV_FILE="$TMP/empty.env"
touch "$BHC_ENV_FILE"
BHC_WIZ_NGINX_MODE="uvicorn_selfsigned"
BHC_WIZ_BACKEND_PORT="8005"
assert_eq "$(bhc_primary_scheme)" "https" "wizard -> https"
assert_eq "$(bhc_resolve_port)" "8005" "wizard port"

echo "[test] USE_HTTPS in .env"
cat >"$TMP/https.env" <<'EOF'
USE_HTTPS=true
SSL_CERT=/etc/ssl/certs/adminpanelaz.crt
BACKEND_PORT=8000
EOF
BHC_ENV_FILE="$TMP/https.env"
BHC_WIZ_NGINX_MODE=""
assert_eq "$(bhc_primary_scheme)" "https" "env USE_HTTPS -> https"

echo "[test] probe urls fallback"
urls="$(bhc_probe_urls 8000 /api/health)"
assert_urls_contain "$urls" "https://127.0.0.1:8000/api/health" "https url"
assert_urls_contain "$urls" "http://127.0.0.1:8000/api/health" "http fallback"

echo "[test] port from backend.log"
BHC_BACKEND_LOG="$TMP/backend.log"
cat >"$BHC_BACKEND_LOG" <<'EOF'
INFO:     Started server process [1]
INFO:     Uvicorn running on https://0.0.0.0:8005 (Press CTRL+C to quit)
EOF
assert_eq "$(bhc_port_from_backend_log)" "8005" "log port parse"
assert_eq "$(bhc_primary_scheme)" "https" "log -> https"

echo "[test] nginx loopback mode"
cat >"$TMP/nginx.env" <<'EOF'
BEHIND_NGINX=true
BACKEND_PORT=8000
USE_HTTPS=false
EOF
BHC_ENV_FILE="$TMP/nginx.env"
BHC_WIZ_NGINX_MODE="le"
BHC_BACKEND_LOG="$TMP/empty.log"
assert_eq "$(bhc_primary_scheme)" "http" "nginx backend -> http"

echo
echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
