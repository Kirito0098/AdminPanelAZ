#!/usr/bin/env bash
# Assert Cloudflare realip snippet + telegram webhook location in generated nginx blocks.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/backend/.env}"
# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0

assert_contains() {
  local haystack="$1" needle="$2" label="$3"
  if printf '%s' "$haystack" | grep -qF "$needle"; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label (missing: $needle)" >&2
  fi
}

assert_file_contains() {
  local path="$1" needle="$2" label="$3"
  if [[ -f "$path" ]] && grep -qF "$needle" "$path"; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label" >&2
  fi
}

echo "[test] repo cloudflare-realip.conf"
SNIPPET_SRC="$ROOT_DIR/deploy/nginx/cloudflare-realip.conf"
assert_file_contains "$SNIPPET_SRC" "real_ip_header CF-Connecting-IP;" "real_ip_header"
assert_file_contains "$SNIPPET_SRC" "real_ip_recursive on;" "real_ip_recursive"
assert_file_contains "$SNIPPET_SRC" "set_real_ip_from 173.245.48.0/20;" "sample CF IPv4"
assert_file_contains "$SNIPPET_SRC" "set_real_ip_from 2400:cb00::/32;" "sample CF IPv6"

echo "[test] ensure snippet copies into override dir"
export NGINX_SNIPPETS_DIR="$TMP/snippets"
nginx_ensure_cloudflare_realip_snippet
assert_file_contains "$TMP/snippets/cloudflare-realip.conf" "real_ip_header CF-Connecting-IP;" "copied snippet"

echo "[test] root panel location blocks"
ROOT_BLOCKS="$(nginx_root_panel_location_blocks 8000)"
assert_contains "$ROOT_BLOCKS" "location ^~ /api/telegram/webhook/" "root webhook location"
assert_contains "$ROOT_BLOCKS" "include snippets/cloudflare-realip.conf;" "root include realip"
assert_contains "$ROOT_BLOCKS" "proxy_set_header X-Real-IP \$remote_addr;" "root X-Real-IP"
# webhook block must appear before tg-mini
ROOT_WH_LINE="$(printf '%s\n' "$ROOT_BLOCKS" | grep -n 'location ^~ /api/telegram/webhook/' | head -1 | cut -d: -f1)"
ROOT_TG_LINE="$(printf '%s\n' "$ROOT_BLOCKS" | grep -n 'location ^~ /api/tg-mini' | head -1 | cut -d: -f1)"
if [[ -n "$ROOT_WH_LINE" && -n "$ROOT_TG_LINE" && "$ROOT_WH_LINE" -lt "$ROOT_TG_LINE" ]]; then
  pass=$((pass + 1))
  echo "  OK  root webhook before tg-mini"
else
  fail=$((fail + 1))
  echo "  FAIL root webhook before tg-mini (wh=$ROOT_WH_LINE tg=$ROOT_TG_LINE)" >&2
fi

echo "[test] subpath template render"
SUB_BLOCKS="$(nginx_render_subpath_template /panel 8000)"
assert_contains "$SUB_BLOCKS" "location ^~ /panel/api/telegram/webhook/" "subpath webhook location"
assert_contains "$SUB_BLOCKS" "include snippets/cloudflare-realip.conf;" "subpath include realip"
SUB_WH_LINE="$(printf '%s\n' "$SUB_BLOCKS" | grep -n 'location ^~ /panel/api/telegram/webhook/' | head -1 | cut -d: -f1)"
SUB_TG_LINE="$(printf '%s\n' "$SUB_BLOCKS" | grep -n 'location ^~ /panel/api/tg-mini' | head -1 | cut -d: -f1)"
if [[ -n "$SUB_WH_LINE" && -n "$SUB_TG_LINE" && "$SUB_WH_LINE" -lt "$SUB_TG_LINE" ]]; then
  pass=$((pass + 1))
  echo "  OK  subpath webhook before tg-mini"
else
  fail=$((fail + 1))
  echo "  FAIL subpath webhook before tg-mini (wh=$SUB_WH_LINE tg=$SUB_TG_LINE)" >&2
fi

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
