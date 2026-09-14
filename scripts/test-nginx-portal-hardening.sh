#!/usr/bin/env bash
# Hardening: server_names_hash snippet + rollback when nginx -t fails.
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

echo "[test] repo server_names_hash template"
HASH_SRC="$ROOT_DIR/deploy/nginx/adminpanelaz-server-names-hash.conf"
assert_file_contains "$HASH_SRC" "server_names_hash_bucket_size 128;" "bucket_size 128"
assert_file_contains "$HASH_SRC" "server_names_hash_max_size 1024;" "max_size 1024"

echo "[test] ensure copies into conf.d override"
export NGINX_CONF_D_DIR="$TMP/conf.d"
nginx_ensure_server_names_hash
assert_file_contains "$TMP/conf.d/adminpanelaz-server-names-hash.conf" \
  "server_names_hash_bucket_size 128;" "copied hash snippet"

echo "[test] ensure keeps larger operator bucket_size"
printf 'server_names_hash_bucket_size 256;\nserver_names_hash_max_size 2048;\n' \
  >"$TMP/conf.d/adminpanelaz-server-names-hash.conf"
nginx_ensure_server_names_hash
assert_file_contains "$TMP/conf.d/adminpanelaz-server-names-hash.conf" \
  "server_names_hash_bucket_size 256;" "kept larger bucket_size"

echo "[test] nginx_install_site rolls back when nginx -t fails"
export NGINX_SITES_AVAILABLE_DIR="$TMP/sites-available"
export NGINX_SITES_ENABLED_DIR="$TMP/sites-enabled"
mkdir -p "$TMP/bin" "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR"
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
echo "nginx: configuration file test failed" >&2
exit 1
EOF
cat >"$TMP/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "stop" ]]; then
  echo "STOP_CALLED" >>"${SYSTEMCTL_LOG:?}"
fi
exit 0
EOF
chmod +x "$TMP/bin/nginx" "$TMP/bin/systemctl"
export PATH="$TMP/bin:$PATH"
export SYSTEMCTL_LOG="$TMP/systemctl.log"
: >"$SYSTEMCTL_LOG"

DOMAIN="portal.panel.example.com"
BASE="$(nginx_conf_basename "$DOMAIN")"
set +e
( nginx_install_site "server { server_name ${DOMAIN}; }" "$DOMAIN" "true" ) >/dev/null 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]]; then
  ok "install exits non-zero on nginx -t failure"
else
  bad "install should fail when nginx -t fails"
fi
if [[ ! -e "$NGINX_SITES_ENABLED_DIR/$BASE" && ! -L "$NGINX_SITES_ENABLED_DIR/$BASE" ]]; then
  ok "enabled symlink removed after failed install"
else
  bad "enabled symlink still present after failed install"
fi
if [[ ! -f "$NGINX_SITES_AVAILABLE_DIR/$BASE" ]]; then
  ok "new sites-available file removed after failed install"
else
  bad "sites-available file left behind after failed install"
fi

echo "[test] failed install rolls back newly created hash snippet"
rm -rf "$TMP/conf.d"
mkdir -p "$TMP/conf.d"
set +e
( nginx_install_site "server { server_name ${DOMAIN}; }" "$DOMAIN" "true" ) >/dev/null 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 && ! -f "$TMP/conf.d/adminpanelaz-server-names-hash.conf" ]]; then
  ok "new hash snippet removed after failed install"
else
  bad "hash snippet should be rolled back when newly created and nginx -t fails"
fi

echo "[test] nginx_install_site restores previous conf on failed update"
# Pre-seed sufficient hash so ensure is a no-op for this case
mkdir -p "$TMP/conf.d"
cp "$HASH_SRC" "$TMP/conf.d/adminpanelaz-server-names-hash.conf"
PREV="server { server_name old.example.com; }"
printf '%s\n' "$PREV" >"$NGINX_SITES_AVAILABLE_DIR/$BASE"
ln -sf "$NGINX_SITES_AVAILABLE_DIR/$BASE" "$NGINX_SITES_ENABLED_DIR/$BASE"
set +e
( nginx_install_site "server { server_name ${DOMAIN}; listen bad; }" "$DOMAIN" "true" ) >/dev/null 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]]; then
  ok "update exits non-zero on nginx -t failure"
else
  bad "update should fail when nginx -t fails"
fi
if [[ -L "$NGINX_SITES_ENABLED_DIR/$BASE" || -e "$NGINX_SITES_ENABLED_DIR/$BASE" ]]; then
  ok "previous enabled link restored"
else
  bad "enabled link missing after failed update"
fi
if [[ -f "$NGINX_SITES_AVAILABLE_DIR/$BASE" ]] && grep -qF "old.example.com" "$NGINX_SITES_AVAILABLE_DIR/$BASE"; then
  ok "previous sites-available content restored"
else
  bad "previous sites-available content not restored"
fi

echo "[test] standalone guard refuses stop when nginx -t fails"
: >"$SYSTEMCTL_LOG"
set +e
( nginx_assert_config_ok_before_stop ) >/dev/null 2>&1
rc=$?
set -e
if [[ "$rc" -ne 0 ]]; then
  ok "assert_config_ok_before_stop exits non-zero"
else
  bad "assert_config_ok_before_stop should fail when nginx -t fails"
fi
if ! grep -q STOP_CALLED "$SYSTEMCTL_LOG" 2>/dev/null; then
  ok "systemctl stop not invoked by assert helper"
else
  bad "systemctl stop should not run from assert helper"
fi

echo "[test] temp ACME http vhost helpers"
export NGINX_SITES_AVAILABLE_DIR="$TMP/sites-available"
export NGINX_SITES_ENABLED_DIR="$TMP/sites-enabled"
export NGINX_CONF_D_DIR="$TMP/conf.d2"
mkdir -p "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR" "$NGINX_CONF_D_DIR"
# nginx -t will fail in fake dirs — install helper should clean up and return 1
set +e
nginx_install_temp_acme_http_vhost "portal.example.com" "80" >/dev/null 2>&1
acme_rc=$?
set -e
if [[ "$acme_rc" -ne 0 ]]; then
  ok "temp ACME install fails cleanly without real nginx -t"
else
  bad "temp ACME should fail nginx -t in fake root"
fi
base="$(nginx_acme_temp_site_basename "portal.example.com")"
[[ "$base" == "adminpanelaz-acme-portal_example_com" ]] && ok "acme temp basename ($base)" || bad "acme temp basename ($base)"

echo "[test] temp ACME restores sites-enabled/default when nginx -t fails"
DEFAULT_AVAIL="$NGINX_SITES_AVAILABLE_DIR/default"
printf 'server { listen 80 default_server; }\n' >"$DEFAULT_AVAIL"
ln -sf "$DEFAULT_AVAIL" "$NGINX_SITES_ENABLED_DIR/default"
set +e
nginx_install_temp_acme_http_vhost "acme-fail-restore.example.com" "80" >/dev/null 2>&1
set -e
if [[ -L "$NGINX_SITES_ENABLED_DIR/default" ]] && [[ "$(readlink "$NGINX_SITES_ENABLED_DIR/default")" == "$DEFAULT_AVAIL" ]]; then
  ok "default site restored after failed temp ACME install"
else
  bad "default site not restored after failed temp ACME install"
fi
acme_fail_base="$(nginx_acme_temp_site_basename "acme-fail-restore.example.com")"
if [[ ! -f "$NGINX_SITES_ENABLED_DIR/.adminpanelaz-acme-default-stash-${acme_fail_base}" ]]; then
  ok "default stash cleaned after failed temp ACME install"
else
  bad "default stash left behind after failed temp ACME install"
fi

echo "[test] temp ACME remove restores sites-enabled/default"
cat >"$TMP/bin/nginx" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMP/bin/nginx"
ln -sf "$DEFAULT_AVAIL" "$NGINX_SITES_ENABLED_DIR/default"
set +e
nginx_install_temp_acme_http_vhost "acme-remove-restore.example.com" "80" >/dev/null 2>&1
acme_ok_rc=$?
set -e
if [[ "$acme_ok_rc" -eq 0 ]]; then
  ok "temp ACME install succeeds when nginx -t passes"
else
  bad "temp ACME install should succeed with passing nginx -t mock"
fi
if [[ ! -e "$NGINX_SITES_ENABLED_DIR/default" && ! -L "$NGINX_SITES_ENABLED_DIR/default" ]]; then
  ok "default removed while temp ACME vhost active"
else
  bad "default should be absent during temp ACME vhost"
fi
nginx_remove_temp_acme_http_vhost "acme-remove-restore.example.com"
if [[ -L "$NGINX_SITES_ENABLED_DIR/default" ]] && [[ "$(readlink "$NGINX_SITES_ENABLED_DIR/default")" == "$DEFAULT_AVAIL" ]]; then
  ok "default site restored after temp ACME remove"
else
  bad "default site not restored after temp ACME remove"
fi

echo "[test] wait_tcp_port_free succeeds when nothing listens"
# Pick a high port unlikely to be in use
FREE_PORT=58431
if nginx_tcp_port_is_listening "$FREE_PORT"; then
  ok "skip wait test — port unexpectedly busy"
else
  if nginx_wait_tcp_port_free "$FREE_PORT" 2 >/dev/null; then
    ok "wait_tcp_port_free on free port"
  else
    bad "wait_tcp_port_free should succeed on free port"
  fi
fi

echo "[test] wait_tcp_port_free dies while port busy"
if command -v python3 >/dev/null 2>&1 && ! nginx_tcp_port_is_listening "$FREE_PORT"; then
  python3 - <<PY &
import socket, time
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", $FREE_PORT))
s.listen(1)
time.sleep(30)
PY
  listener_pid=$!
  sleep 0.3
  set +e
  ( nginx_wait_tcp_port_free "$FREE_PORT" 3 ) >/dev/null 2>&1
  wait_rc=$?
  set -e
  kill "$listener_pid" 2>/dev/null || true
  wait "$listener_pid" 2>/dev/null || true
  if [[ "$wait_rc" -ne 0 ]]; then
    ok "wait_tcp_port_free dies while port busy"
  else
    bad "wait_tcp_port_free should die while port busy"
  fi
else
  ok "skip busy-port wait test (no python3 or port busy)"
fi

echo "[test] wait_tcp_port_free dies when ss unavailable"
mkdir -p "$TMP/noss-bin"
cat >"$TMP/noss-bin/command" <<'WRAP'
#!/usr/bin/env bash
if [[ "${1:-}" == "-v" && "${2:-}" == "ss" ]]; then
  exit 1
fi
exec /usr/bin/command "$@"
WRAP
chmod +x "$TMP/noss-bin/command"
set +e
(
  enable -n command
  PATH="$TMP/noss-bin:$PATH"
  nginx_wait_tcp_port_free "$FREE_PORT" 1
) >/dev/null 2>&1
ss_wait_rc=$?
set -e
enable command 2>/dev/null || true
if [[ "$ss_wait_rc" -ne 0 ]]; then
  ok "wait_tcp_port_free dies without ss"
else
  bad "wait_tcp_port_free should die when ss unavailable"
fi

echo
echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
