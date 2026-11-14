#!/usr/bin/env bash
# Privacy access log: map/mask for /p/ and /api/public/ tokens.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ENV_FILE="$TMP/.env"
: >"$ENV_FILE"
# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

pass=0
fail=0

ok() {
  pass=$((pass + 1))
  echo "  OK  $1"
}

bad() {
  fail=$((fail + 1))
  echo "  FAIL $1" >&2
}

assert_file_contains() {
  local path="$1" needle="$2" label="$3"
  if [[ -f "$path" ]] && grep -qF "$needle" "$path"; then
    ok "$label"
  else
    bad "$label"
  fi
}

assert_file_matches() {
  local path="$1" pattern="$2" label="$3"
  if [[ -f "$path" ]] && grep -qE "$pattern" "$path"; then
    ok "$label"
  else
    bad "$label"
  fi
}

PRIVACY_SRC="$ROOT_DIR/deploy/nginx/adminpanelaz-privacy-log.conf"

echo "[test] privacy-log template masks portal and public tokens"
assert_file_contains "$PRIVACY_SRC" 'map $request_uri $adminpanelaz_log_uri' "map declaration"
assert_file_contains "$PRIVACY_SRC" '/p(?:/u)?/' "masks /p/ and /p/u/ tokens"
assert_file_contains "$PRIVACY_SRC" 'api/public/' "masks /api/public/ tokens"
assert_file_contains "$PRIVACY_SRC" 'api/telegram/webhook/' "masks webhook path secret"
assert_file_contains "$PRIVACY_SRC" 'log_format adminpanelaz_privacy' "privacy log_format"
assert_file_contains "$PRIVACY_SRC" '$adminpanelaz_log_uri' "log_format uses masked URI"

echo "[test] site templates use privacy log format"
assert_file_contains "$ROOT_DIR/deploy/nginx/adminpanelaz.conf.template" \
  "adminpanelaz_privacy" "panel template uses privacy log"
assert_file_contains "$ROOT_DIR/deploy/nginx/adminpanelaz-portal.conf.template" \
  "adminpanelaz_privacy" "portal template uses privacy log"

echo "[test] nginx_ensure_privacy_log copies snippet into conf.d"
export NGINX_CONF_D_DIR="$TMP/conf.d"
nginx_ensure_privacy_log
assert_file_contains "$TMP/conf.d/adminpanelaz-privacy-log.conf" \
  'map $request_uri $adminpanelaz_log_uri' "copied privacy map"
assert_file_matches "$TMP/conf.d/adminpanelaz-privacy-log.conf" \
  'api/public/' "copied mask covers /api/public/"

echo
echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
