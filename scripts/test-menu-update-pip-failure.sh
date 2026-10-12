#!/usr/bin/env bash
# Ошибка pip при обновлении из меню останавливает обновление: без сборки интерфейса, без обновления
# unit'ов systemd и без подсказки перезапустить панель — иначе новый код запустился бы без зависимостей.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CALLS="$TMP/calls.log"

mkdir -p "$TMP/venv/bin" "$TMP/install/frontend/dist" "$TMP/install/scripts" "$TMP/bin"
echo '{"name":"x"}' >"$TMP/install/frontend/package.json"
cat >"$TMP/venv/bin/pip" <<'EOF'
#!/usr/bin/env bash
echo "pip $*" >>"$CALLS"
exit "${PIP_RC:-0}"
EOF
cat >"$TMP/bin/npm" <<'EOF'
#!/usr/bin/env bash
echo "npm $*" >>"$CALLS"
EOF
cat >"$TMP/install/scripts/refresh-systemd-units.sh" <<'EOF'
#!/usr/bin/env bash
echo "refresh-systemd-units" >>"$CALLS"
EOF
chmod +x "$TMP/venv/bin/pip" "$TMP/bin/npm" "$TMP/install/scripts/refresh-systemd-units.sh"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run_after_pull <код pip>: шаги после git pull из меню с подменёнными pip, npm и refresh-systemd-units
run_after_pull() {
  : >"$CALLS"
  set +e
  PIP_RC="$1" INSTALL_DIR="$TMP/install" VENV_PATH="$TMP/venv" PATH="$TMP/bin:$PATH" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    systemctl() { echo "systemctl $*" >>"$CALLS"; }
    panel_after_pull
  ' bash "$ROOT_DIR" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

PIP_CALL="pip install -q -r $ROOT_DIR/backend/requirements.txt"

echo "[test] pip прошёл: сборка интерфейса, units, подсказка перезапуска"
run_after_pull 0
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out")"
if [[ "$(cat "$CALLS")" == "$PIP_CALL"$'\n'"npm ci"$'\n'"npm run build:all"$'\n'"refresh-systemd-units" ]]; then
  ok "pip, npm ci, build:all, units"
else
  bad "вызовы: $(tr '\n' ';' <"$CALLS")"
fi
grep -q "Перезапустите панель" "$TMP/out" && ok "подсказка перезапуска" || bad "нет подсказки: $(cat "$TMP/out")"

echo "[test] pip упал: обновление остановлено"
run_after_pull 1
[[ "$rc" -ne 0 ]] && ok "код ошибки" || bad "ошибка pip не вернула ошибку"
[[ "$(cat "$CALLS")" == "$PIP_CALL" ]] && ok "после pip ничего не запускалось" || bad "вызовы: $(tr '\n' ';' <"$CALLS")"
! grep -q "Перезапустите панель" "$TMP/out" && ok "перезапуск не предложен" || bad "после ошибки pip предложен перезапуск"
grep -qF -- "--after-pull" "$TMP/out" && ok "команда для повтора" || bad "нет команды для повтора: $(cat "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
