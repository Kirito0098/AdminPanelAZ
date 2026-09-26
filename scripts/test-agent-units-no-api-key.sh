#!/usr/bin/env bash
# API-ключи агентов живут только в *_agent.env (600): unit-файлы и `systemctl show` читает любой пользователь.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FAKE_ROOT="$TMP_DIR/repo"
UNIT_DIR="$TMP_DIR/units"
mkdir -p "$FAKE_ROOT/scripts" "$FAKE_ROOT/systemd" "$FAKE_ROOT/backend" "$UNIT_DIR" "$TMP_DIR/bin"
cp "$ROOT_DIR"/scripts/install-node-systemd.sh "$ROOT_DIR"/scripts/install-proxy-systemd.sh \
  "$ROOT_DIR"/scripts/refresh-systemd-units.sh "$ROOT_DIR"/scripts/lib-agent-key.sh "$FAKE_ROOT/scripts/" 2>/dev/null || true
cp "$ROOT_DIR"/systemd/adminpanelaz-node.service "$ROOT_DIR"/systemd/adminpanelaz-proxy.service "$FAKE_ROOT/systemd/"

for script in install-node-systemd.sh install-proxy-systemd.sh refresh-systemd-units.sh; do
  if ! grep -q 'SYSTEMD_UNIT_DIR' "$FAKE_ROOT/scripts/$script"; then
    echo "  FAIL $script не поддерживает SYSTEMD_UNIT_DIR — тест записал бы unit в /etc/systemd/system" >&2
    exit 1
  fi
done

cat >"$TMP_DIR/bin/id" <<'EOF'
#!/usr/bin/env bash
if [[ "$#" -eq 1 && "$1" == "-u" ]]; then echo 0; else exec /usr/bin/id "$@"; fi
EOF
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP_DIR/bin/systemctl"
chmod +x "$TMP_DIR/bin/id" "$TMP_DIR/bin/systemctl"

run() {
  PATH="$TMP_DIR/bin:$PATH" \
    SYSTEMD_UNIT_DIR="$UNIT_DIR" \
    INSTALL_FROM_INSTALL_SH=1 \
    INSTALL_USER="$(id -un)" \
    INSTALL_GROUP="$(id -gn)" \
    NODE_AGENT_STATE_DIR="$TMP_DIR/node-state" \
    PROXY_AGENT_STATE_DIR="$TMP_DIR/proxy-state" \
    "$@" >/dev/null
}

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

NODE_ENV="$FAKE_ROOT/backend/node_agent.env"
PROXY_ENV="$FAKE_ROOT/backend/proxy_agent.env"
NODE_UNIT="$UNIT_DIR/adminpanelaz-node.service"
PROXY_UNIT="$UNIT_DIR/adminpanelaz-proxy.service"

echo "[test] установка unit'а node agent: ключ только в node_agent.env с правами 600"
run env NODE_AGENT_API_KEY=node-key-0123456789abcdef0123 "$FAKE_ROOT/scripts/install-node-systemd.sh"
grep -q 'node-key-0123456789abcdef0123' "$NODE_UNIT" && fail "ключ попал в unit"
grep -q 'NODE_AGENT_API_KEY' "$NODE_UNIT" && fail "в unit осталась переменная ключа"
grep -qx 'NODE_AGENT_API_KEY=node-key-0123456789abcdef0123' "$NODE_ENV" || fail "ключа нет в node_agent.env"
[[ "$(stat -c %a "$NODE_ENV")" == 600 ]] || fail "node_agent.env должен быть 600"
echo "  OK"

echo "[test] повторная установка со старым ключом не затирает ключ после ротации"
printf 'ANTIZAPRET_PATH=/root/antizapret\nNODE_AGENT_API_KEY=rotated-key-abcdef0123456789abcd\n' >"$NODE_ENV"
chmod 644 "$NODE_ENV"
run env NODE_AGENT_API_KEY=node-key-0123456789abcdef0123 "$FAKE_ROOT/scripts/install-node-systemd.sh"
grep -qx 'NODE_AGENT_API_KEY=rotated-key-abcdef0123456789abcd' "$NODE_ENV" || fail "ротированный ключ потерян"
grep -qx 'ANTIZAPRET_PATH=/root/antizapret' "$NODE_ENV" || fail "остальные значения потеряны"
[[ "$(stat -c %a "$NODE_ENV")" == 600 ]] || fail "права node_agent.env должны стать 600"
echo "  OK"

echo "[test] плейсхолдер в node_agent.env заменяется настоящим ключом"
printf 'NODE_AGENT_API_KEY=change-me-node-agent-key\n' >"$NODE_ENV"
run env NODE_AGENT_API_KEY='k3y|with&sed/chars-0123456789ab' "$FAKE_ROOT/scripts/install-node-systemd.sh"
grep -qxF 'NODE_AGENT_API_KEY=k3y|with&sed/chars-0123456789ab' "$NODE_ENV" || fail "плейсхолдер не заменён"
[[ "$(grep -c '^NODE_AGENT_API_KEY=' "$NODE_ENV")" == 1 ]] || fail "ключ продублирован"
echo "  OK"

echo "[test] установка unit'а proxy agent: ключ только в proxy_agent.env с правами 600"
run env PROXY_AGENT_API_KEY=proxy-key-0123456789abcdef012 "$FAKE_ROOT/scripts/install-proxy-systemd.sh"
grep -q 'PROXY_AGENT_API_KEY' "$PROXY_UNIT" && fail "в unit осталась переменная ключа"
grep -qx 'PROXY_AGENT_API_KEY=proxy-key-0123456789abcdef012' "$PROXY_ENV" || fail "ключа нет в proxy_agent.env"
[[ "$(stat -c %a "$PROXY_ENV")" == 600 ]] || fail "proxy_agent.env должен быть 600"
echo "  OK"

echo "[test] обновление старых unit'ов переносит ключ из unit в env-файл и убирает его из unit"
rm -f "$NODE_ENV" "$PROXY_ENV"
sed "s|/opt/AdminPanelAZ|$FAKE_ROOT|g" "$ROOT_DIR/systemd/adminpanelaz-node.service" >"$NODE_UNIT"
printf 'Environment=NODE_AGENT_API_KEY=legacy-node-key-0123456789abcd\n' >>"$NODE_UNIT"
sed "s|/opt/AdminPanelAZ|$FAKE_ROOT|g" "$ROOT_DIR/systemd/adminpanelaz-proxy.service" >"$PROXY_UNIT"
printf 'Environment=PROXY_AGENT_API_KEY=legacy-proxy-key-0123456789ab\n' >>"$PROXY_UNIT"
run env REFRESH_PANEL=0 "$FAKE_ROOT/scripts/refresh-systemd-units.sh"
grep -q 'AGENT_API_KEY' "$NODE_UNIT" "$PROXY_UNIT" && fail "ключ остался в unit после обновления"
grep -qx 'NODE_AGENT_API_KEY=legacy-node-key-0123456789abcd' "$NODE_ENV" || fail "ключ node не перенесён"
grep -qx 'PROXY_AGENT_API_KEY=legacy-proxy-key-0123456789ab' "$PROXY_ENV" || fail "ключ proxy не перенесён"
[[ "$(stat -c %a "$NODE_ENV")" == 600 && "$(stat -c %a "$PROXY_ENV")" == 600 ]] || fail "env-файлы должны быть 600"
echo "  OK"

echo "All agent unit key checks passed."
