#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# Не рабочий backend/.env: библиотека пишет в ENV_FILE.
ENV_FILE="$TMP/.env"
: >"$ENV_FILE"
# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

pass=0; fail=0
ok() { pass=$((pass+1)); echo "  OK  $1"; }
bad() { fail=$((fail+1)); echo "  FAIL $1" >&2; }

assert_file_contains() {
  local path="$1" needle="$2" label="$3"
  if [[ -f "$path" ]] && grep -qF "$needle" "$path"; then
    ok "$label"
  else
    bad "$label"
  fi
}

echo "[test] suggest_portal_domain parity"
got="$(nginx_suggest_portal_domain "panel.example.com")"
[[ "$got" == "portal.example.com" ]] && ok "panel.* → portal.*" || bad "got=$got"
got="$(nginx_suggest_portal_domain "vpn.example.com")"
[[ "$got" == "portal.vpn.example.com" ]] && ok "other subdomain" || bad "got=$got"
got="$(nginx_suggest_portal_domain "portal.example.com")"
[[ "$got" == "clients.example.com" ]] && ok "panel already portal.*" || bad "got=$got"

if nginx_is_nested_portal_host "portal.panel.example.com" "panel.example.com"; then
  ok "nested detected"
else
  bad "nested not detected"
fi
if nginx_is_nested_portal_host "portal.example.com" "panel.example.com"; then
  bad "sibling should not be nested"
else
  ok "sibling not nested"
fi

echo "[test] --check reports hash_bucket_low"
export ENV_FILE="$TMP/env"
export NGINX_CONF_D_DIR="$TMP/conf.d"
export NGINX_SITES_AVAILABLE_DIR="$TMP/sites-available"
export NGINX_SITES_ENABLED_DIR="$TMP/sites-enabled"
mkdir -p "$TMP/bin" "$NGINX_CONF_D_DIR" "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR"
printf 'DOMAIN=panel.example.com\nPUBLISH_MODE=nginx_le\n' >"$ENV_FILE"
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMP/bin/nginx"
export PATH="$TMP/bin:$PATH"

out="$(PORTAL_DOMAIN=portal.example.com bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --check)"
echo "$out" | grep -q 'READY=false' && ok "check not ready" || bad "READY=$out"
echo "$out" | grep -q 'hash_bucket_low' && ok "issue hash" || bad "issues=$out"

echo "[test] --prepare installs hash and READY when clean"
out="$(PORTAL_DOMAIN=portal.example.com bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --prepare)"
echo "$out" | grep -q 'READY=true' && ok "prepare ready" || bad "prepare READY=$out"
assert_file_contains "$TMP/conf.d/adminpanelaz-server-names-hash.conf" \
  "server_names_hash_bucket_size 128;" "hash written"
grep -q '^PORTAL_DOMAIN=portal.example.com$' "$ENV_FILE" && ok "env set" || bad "env not set"

echo "[test] nested host prepare keeps portal.panel.* (no migrate)"
printf 'DOMAIN=panel.example.com\nPUBLISH_MODE=nginx_le\nPORTAL_DOMAIN=portal.panel.example.com\n' >"$ENV_FILE"
out="$(PORTAL_DOMAIN=portal.panel.example.com bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --prepare)"
echo "$out" | grep -q 'READY=true' && ok "nested prepare ready" || bad "nested READY=$out"
mig="$(echo "$out" | grep '^MIGRATED_TO=' | head -1 | cut -d= -f2-)"
[[ -z "$mig" ]] && ok "MIGRATED_TO empty" || bad "MIGRATED_TO=$mig"
echo "$out" | grep -qv 'nested_portal_host' && ok "no nested issue on prepare" || bad "nested still flagged: $out"
grep -q '^PORTAL_DOMAIN=portal.panel.example.com$' "$ENV_FILE" && ok "nested env kept" || bad "env rewritten: $(grep PORTAL_DOMAIN "$ENV_FILE" || true)"

echo "[test] stale portal vhost removed on prepare"
printf 'DOMAIN=panel.example.com\nPUBLISH_MODE=nginx_le\nPORTAL_DOMAIN=portal.example.com\n' >"$ENV_FILE"
PORTAL_BASE="$(nginx_conf_basename "portal.example.com")"
export PORTAL_BASE
printf 'server { listen 443 ssl; BROKEN ; }\n' >"$NGINX_SITES_AVAILABLE_DIR/$PORTAL_BASE"
ln -sf "$NGINX_SITES_AVAILABLE_DIR/$PORTAL_BASE" "$NGINX_SITES_ENABLED_DIR/$PORTAL_BASE"
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "-t" ]]; then
  if [[ -n "${PORTAL_BASE:-}" && -e "${NGINX_SITES_ENABLED_DIR:-/etc/nginx/sites-enabled}/${PORTAL_BASE}" ]]; then
    echo "nginx: [emerg] broken portal vhost" >&2
    exit 1
  fi
  exit 0
fi
exit 0
EOF
chmod +x "$TMP/bin/nginx"

out="$(PORTAL_DOMAIN=portal.example.com bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --check)"
echo "$out" | grep -q 'READY=false' && ok "stale check not ready" || bad "READY=$out"
echo "$out" | grep -q 'nginx_t_fail' && ok "nginx_t_fail flagged" || bad "no nginx_t_fail: $out"
out="$(PORTAL_DOMAIN=portal.example.com bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --prepare)"
echo "$out" | grep -q 'READY=true' && ok "stale prepare ready" || bad "prepare not ready: $out"
if [[ ! -e "$NGINX_SITES_ENABLED_DIR/$PORTAL_BASE" && ! -f "$NGINX_SITES_AVAILABLE_DIR/$PORTAL_BASE" ]]; then
  ok "stale site removed"
else
  bad "stale site still present"
fi

echo "[test] unrelated broken site must not delete portal vhost"
printf 'DOMAIN=panel.example.com\nPUBLISH_MODE=nginx_le\nPORTAL_DOMAIN=portal.example.com\n' >"$ENV_FILE"
PORTAL_BASE="$(nginx_conf_basename "portal.example.com")"
OTHER_BASE="$(nginx_conf_basename "other.example.com")"
export PORTAL_BASE OTHER_BASE
printf 'server { listen 443 ssl; OK ; }\n' >"$NGINX_SITES_AVAILABLE_DIR/$PORTAL_BASE"
ln -sf "$NGINX_SITES_AVAILABLE_DIR/$PORTAL_BASE" "$NGINX_SITES_ENABLED_DIR/$PORTAL_BASE"
printf 'server { listen 443 ssl; BROKEN ; }\n' >"$NGINX_SITES_AVAILABLE_DIR/$OTHER_BASE"
ln -sf "$NGINX_SITES_AVAILABLE_DIR/$OTHER_BASE" "$NGINX_SITES_ENABLED_DIR/$OTHER_BASE"
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "-t" ]]; then
  if [[ -n "${OTHER_BASE:-}" && -e "${NGINX_SITES_ENABLED_DIR:-/etc/nginx/sites-enabled}/${OTHER_BASE}" ]]; then
    echo "nginx: [emerg] unrelated site broken" >&2
    exit 1
  fi
  exit 0
fi
exit 0
EOF
chmod +x "$TMP/bin/nginx"

out="$(PORTAL_DOMAIN=portal.example.com bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --prepare)"
echo "$out" | grep -q 'READY=false' && ok "unrelated prepare still not ready" || bad "unrelated READY=$out"
if [[ -e "$NGINX_SITES_ENABLED_DIR/$PORTAL_BASE" && -f "$NGINX_SITES_AVAILABLE_DIR/$PORTAL_BASE" ]]; then
  ok "portal vhost kept"
else
  bad "portal vhost was deleted"
fi

echo "[test] publish_mode_missing is warning-only"
rm -f "$NGINX_SITES_ENABLED_DIR"/* "$NGINX_SITES_AVAILABLE_DIR"/* 2>/dev/null || true
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMP/bin/nginx"
rm -f "$NGINX_CONF_D_DIR/adminpanelaz-server-names-hash.conf"
cp "$ROOT_DIR/deploy/nginx/adminpanelaz-server-names-hash.conf" "$NGINX_CONF_D_DIR/adminpanelaz-server-names-hash.conf"
printf 'DOMAIN=panel.example.com\nPORTAL_DOMAIN=portal.example.com\n' >"$ENV_FILE"
out="$(bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --check)"
echo "$out" | grep -q 'READY=true' && ok "warning does not block" || bad "warning blocked: $out"
echo "$out" | grep -q 'publish_mode_missing' && ok "warning present" || bad "no warning: $out"

echo "[test] --check flags missing_portal_domain"
printf 'DOMAIN=panel.example.com\nPUBLISH_MODE=nginx_le\n' >"$ENV_FILE"
out="$(bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --check)"
echo "$out" | grep -q 'READY=false' && ok "missing portal blocks" || bad "missing portal READY: $out"
echo "$out" | grep -q 'missing_portal_domain' && ok "missing portal issue" || bad "missing portal issue missing: $out"
echo "$out" | grep -q 'SUGGESTED_PORTAL_DOMAIN=portal.example.com' && ok "suggested emitted" || bad "suggested missing: $out"

echo "[test] --check flags host_equals_panel"
printf 'DOMAIN=panel.example.com\nPUBLISH_MODE=nginx_le\nPORTAL_DOMAIN=panel.example.com\n' >"$ENV_FILE"
out="$(bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --check)"
echo "$out" | grep -q 'host_equals_panel' && ok "equals issue" || bad "no equals issue: $out"
echo "$out" | grep -q 'READY=false' && ok "equals blocks" || bad "equals READY: $out"
echo "$out" | grep -q 'SUGGESTED_PORTAL_DOMAIN=portal.example.com' && ok "equals suggested" || bad "equals suggested missing: $out"

echo "[test] --check flags env_mismatch when PORTAL_DOMAIN passed"
printf 'DOMAIN=panel.example.com\nPUBLISH_MODE=nginx_le\nPORTAL_DOMAIN=portal.example.com\n' >"$ENV_FILE"
out="$(PORTAL_DOMAIN=portal2.example.com bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --check)"
echo "$out" | grep -q 'env_mismatch' && ok "env_mismatch issue" || bad "no env_mismatch: $out"
echo "$out" | grep -q 'READY=false' && ok "env_mismatch blocks" || bad "env_mismatch READY: $out"

echo "[test] --check allows nested portal.panel.* host"
cp "$ROOT_DIR/deploy/nginx/adminpanelaz-server-names-hash.conf" "$NGINX_CONF_D_DIR/adminpanelaz-server-names-hash.conf"
printf 'DOMAIN=panel.example.com\nPUBLISH_MODE=nginx_le\nPORTAL_DOMAIN=portal.panel.example.com\n' >"$ENV_FILE"
out="$(bash "$ROOT_DIR/scripts/nginx-portal-readiness.sh" --check)"
echo "$out" | grep -qv 'nested_portal_host' && ok "no nested issue" || bad "nested still flagged: $out"
echo "$out" | grep -q 'READY=true' && ok "nested check ready" || bad "nested READY: $out"
echo "$out" | grep -q 'PORTAL_DOMAIN=portal.panel.example.com' && ok "nested portal in trailer" || bad "portal trailer: $out"

echo "pass=$pass fail=$fail"
[[ "$fail" -eq 0 ]]
