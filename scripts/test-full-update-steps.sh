#!/usr/bin/env bash
# Шаги полного обновления по отдельности: apt (только отсутствующие пакеты, --no-upgrade), pip, интерфейс,
# unit'ы systemd, firewall и DDNS. apt-get, dpkg, pip, npm, systemctl, ufw, iptables и id подменены;
# refresh-systemd-units.sh — фальшивый скрипт во временной установке.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CALLS="$TMP/calls.log"
INSTALL="$TMP/install"
mkdir -p "$INSTALL/backend" "$INSTALL/scripts" "$TMP/units" "$TMP/venv/bin"
cat >"$TMP/venv/bin/python" <<'EOF'
#!/usr/bin/env bash
echo 3.12.3
EOF
cat >"$TMP/venv/bin/pip" <<'EOF'
#!/usr/bin/env bash
echo "pip $*" >>"$CALLS"
[[ "${PIP_FAIL:-0}" != 1 ]]
EOF
cat >"$INSTALL/scripts/refresh-systemd-units.sh" <<'EOF'
#!/usr/bin/env bash
echo "refresh SYSTEMD_UNIT_DIR=$SYSTEMD_UNIT_DIR" >>"$CALLS"
[[ "${REFRESH_FAIL:-0}" != 1 ]]
EOF
chmod +x "$TMP/venv/bin/python" "$TMP/venv/bin/pip"
BASE="python3-pip git curl build-essential ca-certificates pkg-config libffi-dev libssl-dev vnstat"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

with_units() {
  rm -rf "${TMP:?}/units"
  mkdir -p "$TMP/units"
  local f
  for f in "$@"; do
    touch "$TMP/units/$f"
  done
}

# run <код>: код в bash -c с подключённым scripts/full-update.sh; строки итога — в $TMP/state (см. row),
# вывод — $TMP/out. INSTALLED — пакеты, которые dpkg -s видит установленными; APT_FAIL=1 — apt-get install
# с ошибкой; UFW_ADDED — вывод ufw show added; VENV — каталог venv (по умолчанию $TMP/venv).
run() {
  : >"$CALLS"
  : >"$TMP/state"
  set +e
  env -u LC_ALL -u LC_CTYPE -u SSH_CONNECTION LANG=C.UTF-8 NO_COLOR=1 INSTALL_DIR="$INSTALL" \
    VENV_PATH="${VENV:-$TMP/venv}" SYSTEMD_UNIT_DIR="$TMP/units" DDNS_CONFIG="$TMP/ddns.env" \
    FU_TEST_STATE="$TMP/state" bash -c '
    set -euo pipefail
    source "$1/scripts/full-update.sh"
    FU_STATE="$FU_TEST_STATE"
    require_root() { :; }
    systemctl() {
      case "$1" in
        is-active) return 1 ;;
        *) echo "systemctl $*" >>"$CALLS" ;;
      esac
    }
    dpkg() {
      case " ${INSTALLED:-} " in
        *" $2 "*) printf "Package: %s\nStatus: install ok installed\n" "$2" ;;
        *) echo "dpkg-query: package $2 is not installed" >&2; return 1 ;;
      esac
    }
    apt-get() { echo "apt-get $*" >>"$CALLS"; [[ "$1" != install || "${APT_FAIL:-0}" != 1 ]]; }
    panel_build_frontend() { echo "npm" >>"$CALLS"; }
    ufw() {
      case "$1" in
        show) printf "%s\n" "${UFW_ADDED:-}" ;;
        status) echo "Status: active" ;;
        *) echo "ufw $*" >>"$CALLS" ;;
      esac
    }
    sshd() { echo "port 22"; }
    ss() { :; }
    eval "$2"
  ' bash "$ROOT_DIR" "$1" >"$TMP/out" 2>&1
  set -e
}

calls() { tr '\n' ';' <"$CALLS"; }
# row <шаг>: «статус|подробности» последней строки итога шага
row() { awk -F'\t' -v k="$1" '$1 == k { v = $2 "|" $3 } END { print v }' "$TMP/state"; }

echo "[test] apt: все пакеты на месте — apt-get не вызывается"
INSTALLED="$BASE python3.12 python3.12-venv python3.12-dev" run 'fu_run apt fu_step_apt'
[[ "$(row apt)" == "ok|доустановлено: 0" && "$(calls)" == "" ]] && ok "доустановлено: 0, без apt-get" \
  || bad "итог: $(row apt), вызовы: $(calls)"

echo "[test] apt: только отсутствующие пакеты, с --no-upgrade; Python — версии venv"
INSTALLED="${BASE% vnstat} python3.12 python3.12-venv" run 'fu_run apt fu_step_apt'
[[ "$(calls)" == "apt-get update -qq;apt-get install -y --no-upgrade vnstat python3.12-dev;" ]] \
  && ok "apt-get install -y --no-upgrade vnstat python3.12-dev" || bad "вызовы: $(calls)"
[[ "$(row apt)" == "ok|доустановлено: 2 (vnstat python3.12-dev)" ]] && ok "итог" || bad "итог: $(row apt)"

echo "[test] apt: ошибка apt-get — «ошибка», обновление продолжается"
INSTALLED="${BASE% vnstat}" APT_FAIL=1 run 'fu_run apt fu_step_apt; echo "stopped=$FU_STOPPED"'
[[ "$(row apt)" == "ошибка|не доустановлено: vnstat python3.12 python3.12-venv python3.12-dev" ]] \
  && grep -qx "stopped=false" "$TMP/out" && ok "предупреждение без стопа" || bad "итог: $(row apt); $(cat "$TMP/out")"

echo "[test] apt: список пакетов общий с install.sh"
grep -qF 'apt-get install -y "${ADMINPANELAZ_APT_PACKAGES[@]}"' "$ROOT_DIR/install.sh" \
  && ok "install_system_deps ставит ADMINPANELAZ_APT_PACKAGES" || bad "install.sh не использует общий список"

echo "[test] pip: install -r backend/requirements.txt из venv"
run 'fu_run pip fu_step_pip'
[[ "$(calls)" == "pip install -q -r $INSTALL/backend/requirements.txt;" && "$(row pip)" == "ok|" ]] && ok "pip install" \
  || bad "итог: $(row pip), вызовы: $(calls)"

echo "[test] pip: ошибка — стоп"
PIP_FAIL=1 run 'fu_run pip fu_step_pip; echo "stopped=$FU_STOPPED"'
[[ "$(row pip)" == "ошибка|pip install не прошёл — панель не перезапускалась" ]] && grep -qx "stopped=true" "$TMP/out" \
  && ok "стоп" || bad "итог: $(row pip); $(cat "$TMP/out")"

echo "[test] pip: нет venv — стоп с путём"
VENV="$TMP/no-venv" run 'fu_run pip fu_step_pip; echo "stopped=$FU_STOPPED"'
[[ "$(row pip)" == "ошибка|нет $TMP/no-venv/bin/pip" && "$(calls)" == "" ]] && grep -qx "stopped=true" "$TMP/out" \
  && ok "стоп" || bad "итог: $(row pip); $(cat "$TMP/out")"

echo "[test] интерфейс: сборка только при панели"
with_units adminpanelaz.service
run 'fu_run frontend fu_step_frontend'
[[ "$(calls)" == "npm;" && "$(row frontend)" == "ok|" ]] && ok "панель — сборка" || bad "итог: $(row frontend), вызовы: $(calls)"
with_units adminpanelaz-node.service
run 'fu_run frontend fu_step_frontend'
[[ "$(calls)" == "" && "$(row frontend)" == "пропущен|нет панели" ]] && ok "узел — пропущен" \
  || bad "итог: $(row frontend), вызовы: $(calls)"

echo "[test] systemd: unit'ы всех установленных ролей из шаблонов"
with_units adminpanelaz.service adminpanelaz-node.service adminpanelaz-proxy.service
run 'fu_run systemd fu_step_systemd'
[[ "$(calls)" == "refresh SYSTEMD_UNIT_DIR=$TMP/units;" \
  && "$(row systemd)" == "ok|adminpanelaz, adminpanelaz-node, adminpanelaz-proxy" ]] && ok "refresh-systemd-units.sh" \
  || bad "итог: $(row systemd), вызовы: $(calls)"
REFRESH_FAIL=1 run 'fu_run systemd fu_step_systemd; echo "stopped=$FU_STOPPED"'
[[ "$(row systemd)" == "ошибка|refresh-systemd-units.sh завершился с ошибкой — проверьте unit'ы вручную" ]] \
  && grep -qx "stopped=false" "$TMP/out" && ok "ошибка без стопа" || bad "итог: $(row systemd); $(cat "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
