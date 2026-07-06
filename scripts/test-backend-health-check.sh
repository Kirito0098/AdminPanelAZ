#!/usr/bin/env bash
# Тесты health-check для всех режимов публикации install.sh (без запущенного backend).
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

assert_urls_first() {
  local urls="$1" want="$2" label="$3"
  local first
  first="$(printf '%s\n' "$urls" | head -1)"
  if [[ "$first" == "$want" ]]; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label (first='$first' want='$want')" >&2
  fi
}

reset_bhc() {
  BHC_ENV_FILE="$TMP/empty.env"
  touch "$BHC_ENV_FILE"
  BHC_WIZ_NGINX_MODE=""
  BHC_WIZ_BACKEND_PORT=""
  BHC_BACKEND_PORT=""
  BHC_BACKEND_LOG="$TMP/empty.log"
  : >"$BHC_BACKEND_LOG"
}

test_mode_scheme() {
  local mode="$1" want_scheme="$2"
  reset_bhc
  BHC_WIZ_NGINX_MODE="$mode"
  BHC_WIZ_BACKEND_PORT="8000"
  assert_eq "$(bhc_primary_scheme)" "$want_scheme" "mode=$mode -> $want_scheme"
}

echo "[test] все 8 режимов публикации (wizard -> схема health-check)"
test_mode_scheme "le" "http"
test_mode_scheme "selfsigned" "http"
test_mode_scheme "nginx_custom" "http"
test_mode_scheme "uvicorn_le" "https"
test_mode_scheme "uvicorn_custom" "https"
test_mode_scheme "uvicorn_selfsigned" "https"
test_mode_scheme "none" "http"
test_mode_scheme "http_direct" "http"

echo "[test] .env перекрывает wizard (nginx loopback)"
cat >"$TMP/nginx.env" <<'EOF'
BEHIND_NGINX=true
BACKEND_PORT=8000
USE_HTTPS=false
EOF
BHC_ENV_FILE="$TMP/nginx.env"
BHC_WIZ_NGINX_MODE="le"
assert_eq "$(bhc_primary_scheme)" "http" "BEHIND_NGINX + USE_HTTPS=false -> http"

echo "[test] uvicorn .env"
cat >"$TMP/https.env" <<'EOF'
USE_HTTPS=true
SSL_CERT=/etc/ssl/certs/adminpanelaz.crt
BACKEND_PORT=8000
BEHIND_NGINX=false
EOF
BHC_ENV_FILE="$TMP/https.env"
BHC_WIZ_NGINX_MODE=""
assert_eq "$(bhc_primary_scheme)" "https" "USE_HTTPS=true -> https"

echo "[test] Let's Encrypt не выдан: wizard uvicorn_le, .env без TLS"
reset_bhc
BHC_WIZ_NGINX_MODE="uvicorn_le"
BHC_WIZ_BACKEND_PORT="8000"
assert_eq "$(bhc_primary_scheme)" "https" "uvicorn_le wizard prefers https"
urls="$(bhc_probe_urls 8000 /api/health)"
assert_urls_first "$urls" "https://127.0.0.1:8000/api/health" "primary https"
assert_urls_contain "$urls" "http://127.0.0.1:8000/api/health" "fallback http for LE fail"

echo "[test] USE_HTTPS=false явно в .env при uvicorn wizard"
cat >"$TMP/no-tls.env" <<'EOF'
USE_HTTPS=false
BACKEND_PORT=8000
EOF
BHC_ENV_FILE="$TMP/no-tls.env"
BHC_WIZ_NGINX_MODE="uvicorn_selfsigned"
assert_eq "$(bhc_primary_scheme)" "http" "USE_HTTPS=false overrides wizard"

echo "[test] probe urls dual-scheme"
BHC_ENV_FILE="$TMP/https.env"
BHC_WIZ_NGINX_MODE="uvicorn_selfsigned"
urls="$(bhc_probe_urls 8000 /api/health)"
assert_urls_contain "$urls" "https://127.0.0.1:8000/api/health" "https url"
assert_urls_contain "$urls" "http://127.0.0.1:8000/api/health" "http fallback"

echo "[test] порт из backend.log"
BHC_BACKEND_LOG="$TMP/backend.log"
cat >"$BHC_BACKEND_LOG" <<'EOF'
INFO:     Uvicorn running on https://0.0.0.0:8005 (Press CTRL+C to quit)
EOF
assert_eq "$(bhc_port_from_backend_log)" "8005" "log port parse"
assert_eq "$(bhc_primary_scheme)" "https" "log https"

echo "[test] http_direct из лога"
reset_bhc
BHC_WIZ_NGINX_MODE="http_direct"
cat >"$BHC_BACKEND_LOG" <<'EOF'
INFO:     Uvicorn running on http://0.0.0.0:9000 (Press CTRL+C to quit)
EOF
assert_eq "$(bhc_port_from_backend_log)" "9000" "http log port"
assert_eq "$(bhc_primary_scheme)" "http" "http log -> http"

echo "[test] кандидаты портов"
cat >"$TMP/ports.env" <<'EOF'
BACKEND_PORT=8000
USE_HTTPS=true
SSL_CERT=/x.crt
EOF
BHC_ENV_FILE="$TMP/ports.env"
BHC_WIZ_BACKEND_PORT="8005"
BHC_BACKEND_LOG="$TMP/empty.log"
printf '%s\n' \
  "$(bhc_port_candidates | tr '\n' ' ' | sed 's/ $//')" \
  | grep -q '8000 8005' && { pass=$((pass + 1)); echo "  OK  port candidates env+wiz"; } \
  || { fail=$((fail + 1)); echo "  FAIL port candidates" >&2; }

echo
echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
