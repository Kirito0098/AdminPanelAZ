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

assert_count() {
  local haystack="$1" needle="$2" expected="$3" label="$4" actual
  actual="$(printf '%s\n' "$haystack" | grep -cF -- "$needle" || true)"
  if [[ "$actual" -eq "$expected" ]]; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label (expected $expected x '$needle', got $actual)" >&2
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
assert_file_contains "$SNIPPET_SRC" "# snapshot: 2026-08-20" "snapshot date"

echo "[test] repo cloudflare-origin-allow.conf"
ALLOW_SRC="$ROOT_DIR/deploy/nginx/cloudflare-origin-allow.conf"
assert_file_contains "$ALLOW_SRC" "deny all;" "allow deny all"
assert_file_contains "$ALLOW_SRC" "allow 10.0.0.0/8;" "allow RFC1918"
assert_file_contains "$ALLOW_SRC" "allow 173.245.48.0/20;" "allow sample CF"

echo "[test] ensure snippet copies into override dir"
export NGINX_SNIPPETS_DIR="$TMP/snippets"
export NGINX_BACKUPS_DIR="$TMP/backups"
nginx_ensure_cloudflare_realip_snippet
assert_file_contains "$TMP/snippets/cloudflare-realip.conf" "real_ip_header CF-Connecting-IP;" "copied snippet"
nginx_ensure_cloudflare_origin_allow_snippet
assert_file_contains "$TMP/snippets/cloudflare-origin-allow.conf" "deny all;" "copied allow snippet"

echo "[test] ensure backs up when replacing different content"
printf '# stale snippet\n' >"$TMP/snippets/cloudflare-realip.conf"
nginx_ensure_cloudflare_realip_snippet
if compgen -G "$TMP/backups/cloudflare-realip.conf.*.bak" >/dev/null; then
  pass=$((pass + 1))
  echo "  OK  ensure backup created"
else
  fail=$((fail + 1))
  echo "  FAIL ensure backup created" >&2
fi
assert_file_contains "$TMP/snippets/cloudflare-realip.conf" "real_ip_header CF-Connecting-IP;" "ensure replaced stale snippet"
printf '# stale allow snippet\n' >"$TMP/snippets/cloudflare-origin-allow.conf"
nginx_ensure_cloudflare_origin_allow_snippet
if compgen -G "$TMP/backups/cloudflare-origin-allow.conf.*.bak" >/dev/null; then
  pass=$((pass + 1))
  echo "  OK  ensure allow backup created"
else
  fail=$((fail + 1))
  echo "  FAIL ensure allow backup created" >&2
fi
assert_file_contains "$TMP/snippets/cloudflare-origin-allow.conf" "deny all;" "ensure replaced stale allow snippet"

echo "[test] root panel location blocks"
export CLOUDFLARE_PROXY_ENABLED=true CLOUDFLARE_ORIGIN_LOCK=true
ROOT_BLOCKS="$(nginx_root_panel_location_blocks 8000)"
assert_contains "$ROOT_BLOCKS" "location ^~ /api/telegram/webhook/" "root webhook location"
assert_contains "$ROOT_BLOCKS" "include snippets/cloudflare-realip.conf;" "root include realip"
assert_contains "$ROOT_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" "root include origin lock"
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
export CLOUDFLARE_PROXY_ENABLED=true CLOUDFLARE_ORIGIN_LOCK=true
SUB_BLOCKS="$(nginx_render_subpath_template /panel 8000)"
assert_contains "$SUB_BLOCKS" "location ^~ /panel/api/telegram/webhook/" "subpath webhook location"
assert_contains "$SUB_BLOCKS" "include snippets/cloudflare-realip.conf;" "subpath include realip"
assert_contains "$SUB_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" "subpath include origin lock"
SUB_WH_LINE="$(printf '%s\n' "$SUB_BLOCKS" | grep -n 'location ^~ /panel/api/telegram/webhook/' | head -1 | cut -d: -f1)"
SUB_TG_LINE="$(printf '%s\n' "$SUB_BLOCKS" | grep -n 'location ^~ /panel/api/tg-mini' | head -1 | cut -d: -f1)"
if [[ -n "$SUB_WH_LINE" && -n "$SUB_TG_LINE" && "$SUB_WH_LINE" -lt "$SUB_TG_LINE" ]]; then
  pass=$((pass + 1))
  echo "  OK  subpath webhook before tg-mini"
else
  fail=$((fail + 1))
  echo "  FAIL subpath webhook before tg-mini (wh=$SUB_WH_LINE tg=$SUB_TG_LINE)" >&2
fi

echo "[test] include present when CLOUDFLARE_PROXY_ENABLED=true"
export CLOUDFLARE_PROXY_ENABLED=true
ROOT_BLOCKS="$(nginx_root_panel_location_blocks 8000)"
assert_contains "$ROOT_BLOCKS" "include snippets/cloudflare-realip.conf;" "enabled root include"
export CLOUDFLARE_ORIGIN_LOCK=true
ROOT_BLOCKS="$(nginx_root_panel_location_blocks 8000)"
assert_contains "$ROOT_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" "enabled root lock include"
SUB_BLOCKS="$(nginx_render_subpath_template /panel 8000)"
assert_contains "$SUB_BLOCKS" "include snippets/cloudflare-realip.conf;" "enabled subpath include"
assert_contains "$SUB_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" "enabled subpath lock include"

echo "[test] include absent when CLOUDFLARE_PROXY_ENABLED=false"
export CLOUDFLARE_PROXY_ENABLED=false
ROOT_BLOCKS="$(nginx_root_panel_location_blocks 8000)"
SUB_BLOCKS="$(nginx_render_subpath_template /panel 8000)"
if printf '%s' "$ROOT_BLOCKS" | grep -qF "include snippets/cloudflare-realip.conf;"; then
  fail=$((fail + 1))
  echo "  FAIL disabled root still has include" >&2
else
  pass=$((pass + 1))
  echo "  OK  disabled root omits include"
fi
SUB_BLOCKS="$(nginx_render_subpath_template /panel 8000)"
if printf '%s' "$SUB_BLOCKS" | grep -qF "include snippets/cloudflare-realip.conf;"; then
  fail=$((fail + 1))
  echo "  FAIL disabled subpath still has include" >&2
else
  pass=$((pass + 1))
  echo "  OK  disabled subpath omits include"
fi
assert_count "$ROOT_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" 0 "disabled root omits lock include"
assert_count "$SUB_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" 0 "disabled subpath omits lock include"

echo "[test] ensure snippet still runs when proxy disabled"
export CLOUDFLARE_PROXY_ENABLED=false
nginx_ensure_cloudflare_realip_snippet
assert_file_contains "$TMP/snippets/cloudflare-realip.conf" "real_ip_header CF-Connecting-IP;" "ensure snippet when disabled"

echo "[test] realip + origin lock on every panel location"
export CLOUDFLARE_PROXY_ENABLED=true CLOUDFLARE_ORIGIN_LOCK=true
ROOT_BLOCKS="$(nginx_root_panel_location_blocks 8000)"
SUB_BLOCKS="$(nginx_render_subpath_template /panel 8000)"
PORTAL_BLOCKS="$(nginx_portal_location_blocks 8000)"
assert_count "$ROOT_BLOCKS" "include snippets/cloudflare-realip.conf;" 3 "root realip in all 3 locations"
assert_count "$ROOT_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" 3 "root lock in all 3 locations"
assert_count "$SUB_BLOCKS" "include snippets/cloudflare-realip.conf;" 3 "subpath realip in all 3 locations"
assert_count "$SUB_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" 3 "subpath lock in all 3 locations"
assert_count "$PORTAL_BLOCKS" "include snippets/cloudflare-realip.conf;" 5 "portal realip in all proxied locations"
assert_count "$PORTAL_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" 0 "portal has no origin lock"
# allow/deny is evaluated after realip rewrites the address, so it must never share a location with realip
assert_count "$ROOT_BLOCKS$SUB_BLOCKS$PORTAL_BLOCKS" "cloudflare-origin-allow.conf" 0 "no allow snippet in locations"

echo "[test] origin lock only when CLOUDFLARE_ORIGIN_LOCK=true"
export CLOUDFLARE_PROXY_ENABLED=true CLOUDFLARE_ORIGIN_LOCK=false
ROOT_BLOCKS="$(nginx_root_panel_location_blocks 8000)"
SUB_BLOCKS="$(nginx_render_subpath_template /panel 8000)"
assert_count "$ROOT_BLOCKS" "include snippets/cloudflare-realip.conf;" 3 "lock off: root realip kept"
assert_count "$ROOT_BLOCKS$SUB_BLOCKS" "include snippets/cloudflare-origin-lock.conf;" 0 "lock off: no lock include"

echo "[test] origin geo rendered from allow snippet"
GEO="$(nginx_render_cloudflare_origin_geo "$ROOT_DIR/deploy/nginx/cloudflare-origin-allow.conf")"
assert_contains "$GEO" 'geo $realip_remote_addr $adminpanelaz_cf_origin {' "geo keyed by TCP peer"
assert_contains "$GEO" "default 0;" "geo default deny"
assert_contains "$GEO" "173.245.48.0/20 1;" "geo CF IPv4"
assert_contains "$GEO" "2400:cb00::/32 1;" "geo CF IPv6"
assert_contains "$GEO" "127.0.0.1 1;" "geo localhost"
assert_count "$GEO" "allow " 0 "geo has no allow directives"
assert_count "$GEO" "deny all" 0 "geo has no deny directive"

echo "[test] ensure origin snippets writes lock snippet and conf.d geo"
export NGINX_CONF_D_DIR="$TMP/conf.d"
nginx_ensure_cloudflare_origin_snippets
assert_file_contains "$TMP/snippets/cloudflare-origin-allow.conf" "deny all;" "ensure origin: allow source"
assert_file_contains "$TMP/snippets/cloudflare-origin-lock.conf" 'if ($adminpanelaz_cf_origin = 0)' "ensure origin: lock snippet"
assert_file_contains "$TMP/conf.d/adminpanelaz-cloudflare-origin.conf" "173.245.48.0/20 1;" "ensure origin: conf.d geo"

echo "[test] snippets apply regenerates geo and rolls it back on nginx -t failure"
printf 'allow 192.0.2.0/24;\ndeny all;\n' >"$TMP/new-allow.conf"
printf 'real_ip_header CF-Connecting-IP;\n' >"$TMP/new-realip.conf"
GEO_DEST="$TMP/conf.d/adminpanelaz-cloudflare-origin.conf"
GEO_BEFORE="$(cat "$GEO_DEST")"
(
  id() { echo 0; }
  nginx() { return 0; }
  systemctl() { return 0; }
  nginx_cloudflare_snippets_apply "$TMP/new-realip.conf" "$TMP/new-allow.conf"
) >/dev/null 2>&1
assert_file_contains "$GEO_DEST" "192.0.2.0/24 1;" "apply: geo regenerated from new allow list"
cp "$TMP/snippets/cloudflare-origin-allow.conf" "$TMP/allow-applied.conf"
GEO_APPLIED="$(cat "$GEO_DEST")"
printf 'allow 198.51.100.0/24;\ndeny all;\n' >"$TMP/bad-allow.conf"
(
  id() { echo 0; }
  nginx() { return 1; }
  systemctl() { return 0; }
  nginx_cloudflare_snippets_apply "$TMP/new-realip.conf" "$TMP/bad-allow.conf"
) >/dev/null 2>&1 || true
if [[ "$(cat "$GEO_DEST")" == "$GEO_APPLIED" ]] && cmp -s "$TMP/allow-applied.conf" "$TMP/snippets/cloudflare-origin-allow.conf"; then
  pass=$((pass + 1))
  echo "  OK  apply failure: allow + geo restored"
else
  fail=$((fail + 1))
  echo "  FAIL apply failure: allow + geo restored" >&2
fi
[[ "$GEO_BEFORE" != "$GEO_APPLIED" ]] || { fail=$((fail + 1)); echo "  FAIL geo unchanged by apply" >&2; }

echo "[test] nginx behaviour: realip + origin lock (skipped without nginx)"
if command -v nginx >/dev/null 2>&1 && command -v curl >/dev/null 2>&1; then
  NGX="$TMP/ngx"
  mkdir -p "$NGX/snippets" "$NGX/logs"
  printf 'set_real_ip_from 127.0.0.1;\nreal_ip_header CF-Connecting-IP;\nreal_ip_recursive on;\n' >"$NGX/snippets/cloudflare-realip.conf"
  cp "$TMP/snippets/cloudflare-origin-lock.conf" "$NGX/snippets/"
  export CLOUDFLARE_PROXY_ENABLED=true CLOUDFLARE_ORIGIN_LOCK=true
  ngx_run() {
    local allow_body="$1" port="$2"
    printf '%s\n' "$allow_body" >"$NGX/allow.conf"
    {
      printf 'pid %s/nginx.pid;\nerror_log %s/logs/error.log;\nevents {}\nhttp {\n' "$NGX" "$NGX"
      printf '  access_log off;\n  client_body_temp_path %s; proxy_temp_path %s; fastcgi_temp_path %s; uwsgi_temp_path %s; scgi_temp_path %s;\n' "$NGX" "$NGX" "$NGX" "$NGX" "$NGX"
      printf '  map $http_upgrade $connection_upgrade { default upgrade; "" close; }\n'
      nginx_render_cloudflare_origin_geo "$NGX/allow.conf"
      printf '  server { listen 127.0.0.1:%s; location / { return 200 "ip=$http_x_real_ip"; } }\n' "$((port + 1))"
      printf '  server {\n    listen 127.0.0.1:%s;\n' "$port"
      nginx_root_panel_location_blocks "$((port + 1))" | sed "s|include snippets/|include $NGX/snippets/|"
      printf '  }\n}\n'
    } >"$NGX/nginx.conf"
    nginx -p "$NGX" -c "$NGX/nginx.conf" -t -q 2>"$NGX/t.err" || { cat "$NGX/t.err" >&2; return 1; }
    nginx -p "$NGX" -c "$NGX/nginx.conf" 2>/dev/null
    sleep 0.3
    NGX_BODY="$(curl -s -H 'CF-Connecting-IP: 203.0.113.9' "http://127.0.0.1:${port}/api/health")"
    NGX_CODE="$(curl -s -o /dev/null -w '%{http_code}' -H 'CF-Connecting-IP: 203.0.113.9' "http://127.0.0.1:${port}/api/telegram/webhook/x")"
    nginx -p "$NGX" -c "$NGX/nginx.conf" -s stop 2>/dev/null || true
    sleep 0.2
  }
  if ngx_run $'allow 127.0.0.1;\ndeny all;' 18471; then
    assert_contains "$NGX_BODY" "ip=203.0.113.9" "trusted edge: backend sees visitor IP"
    assert_contains "$NGX_CODE" "200" "trusted edge: webhook allowed under origin lock"
  else
    fail=$((fail + 1)); echo "  FAIL nginx -t (trusted edge)" >&2
  fi
  if ngx_run $'allow 198.51.100.0/24;\ndeny all;' 18473; then
    assert_contains "$NGX_CODE" "403" "non-Cloudflare peer: origin lock denies"
  else
    fail=$((fail + 1)); echo "  FAIL nginx -t (untrusted peer)" >&2
  fi
else
  echo "  SKIP nginx/curl not installed"
fi

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
