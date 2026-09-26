#!/usr/bin/env bash
# run-shell-tests.sh роняет тест, который вызывает на хосте изменяющие команды, и пропускает читающие и подменённые.
# Запрещённые вызовы здесь безвредны, даже если охрана сломана: несуществующий unit, цепочка и конфиг.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

run_guarded() {
  local status=0
  "$ROOT_DIR/scripts/run-shell-tests.sh" "$1" >"$TMP/out" 2>&1 || status=$?
  return "$status"
}

echo "[test] изменяющие вызовы на хосте роняют тест, даже если он сам прошёл"
cat >"$TMP/test-writes.sh" <<'EOF'
#!/usr/bin/env bash
systemctl restart adminpanelaz-guard-selftest-missing.service 2>/dev/null || true
iptables -A AZ_GUARD_SELFTEST_MISSING -j RETURN 2>/dev/null || true
nginx -s reload -c /etc/nginx/adminpanelaz-guard-selftest-missing.conf 2>/dev/null || true
exit 0
EOF
run_guarded "$TMP/test-writes.sh" && fail "тест с вызовами на хосте прошёл"
grep -qF "systemctl restart adminpanelaz-guard-selftest-missing.service" "$TMP/out" || fail "systemctl restart не пойман"
grep -qF "iptables -A AZ_GUARD_SELFTEST_MISSING" "$TMP/out" || fail "iptables -A не пойман"
grep -qF "nginx -s reload" "$TMP/out" || fail "nginx -s reload не пойман"
echo "  OK"

echo "[test] читающие вызовы, свой nginx на временном конфиге и подменённые команды проходят"
cat >"$TMP/test-clean.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
systemctl is-active adminpanelaz-guard-selftest-missing.service >/dev/null 2>&1 || true
iptables -S >/dev/null 2>&1 || true
nginx -p "$TMP" -c "$TMP/nginx.conf" -t >/dev/null 2>&1 || true
mkdir -p "$TMP/bin"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/bin/systemctl"
chmod +x "$TMP/bin/systemctl"
PATH="$TMP/bin:\$PATH" systemctl restart nginx
EOF
run_guarded "$TMP/test-clean.sh" || fail "чистый тест упал: $(cat "$TMP/out")"
echo "  OK"

echo "[test] упавший тест без вызовов на хосте тоже роняет прогон"
printf '#!/usr/bin/env bash\nexit 3\n' >"$TMP/test-red.sh"
run_guarded "$TMP/test-red.sh" && fail "упавший тест не уронил прогон"
grep -q "HOST GUARD" "$TMP/out" && fail "ложное срабатывание охраны"
echo "  OK"

echo "All host guard checks passed."
