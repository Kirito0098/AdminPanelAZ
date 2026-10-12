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
export ADMINPANELAZ_MENU_LINK="$TMP/adminpanelaz"
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
# с ошибкой; UFW_ADDED — вывод ufw show added, UFW_STATUS — active|inactive; VENV — каталог venv (по умолчанию $TMP/venv).
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
        status) echo "Status: ${UFW_STATUS:-active}" ;;
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

echo "[test] systemd: ставит команду adminpanelaz, даже если unit'ы не обновились"
touch "$INSTALL/scripts/adminpanel-menu.sh"
run 'fu_run systemd fu_step_systemd'
[[ "$(readlink "$ADMINPANELAZ_MENU_LINK" || true)" == "$INSTALL/scripts/adminpanel-menu.sh" ]] && ok "ссылка создана" \
  || bad "ссылки нет: $(readlink "$ADMINPANELAZ_MENU_LINK" || true); $(cat "$TMP/out")"
rm -f "$ADMINPANELAZ_MENU_LINK"
REFRESH_FAIL=1 run 'fu_run systemd fu_step_systemd'
[[ "$(readlink "$ADMINPANELAZ_MENU_LINK" || true)" == "$INSTALL/scripts/adminpanel-menu.sh" ]] && ok "при ошибке unit'ов" \
  || bad "ссылки нет после ошибки refresh: $(cat "$TMP/out")"
rm -f "$ADMINPANELAZ_MENU_LINK" "$INSTALL/scripts/adminpanel-menu.sh"

PANEL_NGINX_ENV='DOMAIN=panel.example.com
PUBLISH_MODE=nginx_le
BACKEND_PORT=8000
HTTPS_PUBLIC_PORT=443
HTTP_ACME_PORT=80'

echo "[test] firewall: в ufw только правило SSH — не настроен, правила не трогаются"
with_units adminpanelaz.service
printf '%s\n' "$PANEL_NGINX_ENV" >"$INSTALL/backend/.env"
UFW_ADDED="ufw allow 22/tcp comment 'SSH (AdminPanelAZ)'" run 'fu_run firewall fu_step_firewall'
[[ "$(row firewall)" == "пропущен|не настроен" && "$(calls)" == "" ]] && ok "ufw без своих правил — пропущен" \
  || bad "итог: $(row firewall), вызовы: $(calls)"

echo "[test] firewall: iptables без своих правил — не настроен, ни -A, ни -D"
run 'firewall_detect_tool() { echo iptables; }
  iptables() { echo "iptables $*" >>"$CALLS"; [[ "$1" != -C ]]; }
  fu_run firewall fu_step_firewall'
[[ "$(row firewall)" == "пропущен|не настроен" ]] && ok "iptables — пропущен" || bad "итог: $(row firewall); $(cat "$TMP/out")"
grep -qF "iptables -C INPUT -p tcp --dport 8000 ! -s 127.0.0.1 -j DROP" "$CALLS" && ok "проверено правило backend" \
  || bad "вызовы: $(calls)"
! grep -qE '^iptables -(A|D) ' "$CALLS" && ok "правила не менялись" || bad "вызовы: $(calls)"

echo "[test] firewall: ufw настроен — правила панели за nginx заново, ufw не включается"
UFW_ADDED="ufw deny 8000/tcp comment 'AdminPanelAZ backend'" run 'fu_run firewall fu_step_firewall'
[[ "$(row firewall)" == "ok|ufw: правила AdminPanelAZ применены заново" ]] && ok "итог ok" \
  || bad "итог: $(row firewall); $(cat "$TMP/out")"
grep -qxF "ufw deny 8000/tcp comment AdminPanelAZ backend" "$CALLS" && ok "backend закрыт" || bad "вызовы: $(calls)"
grep -qxF "ufw allow 443/tcp comment AdminPanelAZ HTTPS" "$CALLS" \
  && grep -qxF "ufw allow 80/tcp comment AdminPanelAZ HTTP (ACME)" "$CALLS" && ok "443 и 80 открыты" || bad "вызовы: $(calls)"
grep -qxF "ufw reload" "$CALLS" && ok "ufw reload" || bad "вызовы: $(calls)"
UFW_STATUS=inactive UFW_ADDED="ufw deny 8000/tcp comment 'AdminPanelAZ backend'" run 'fu_run firewall fu_step_firewall'
grep -qxF "ufw allow 22/tcp comment SSH (AdminPanelAZ)" "$CALLS" && ! grep -qE '^ufw (--force )?enable' "$CALLS" \
  && ok "неактивный ufw: SSH разрешён, ufw не включён" || bad "вызовы: $(calls)"

echo "[test] firewall: агент без IP панели в node_agent.env — правила не менялись"
with_units adminpanelaz-node.service
printf 'NODE_AGENT_PORT=9100\n' >"$INSTALL/backend/node_agent.env"
UFW_ADDED="ufw deny 9100/tcp comment 'AdminPanelAZ node agent'" run 'fu_run firewall fu_step_firewall'
[[ "$(row firewall)" == "пропущен|IP панели не записан в node_agent.env / proxy_agent.env — правила не менялись" \
  && "$(calls)" == "" ]] && ok "пропущен без IP панели" || bad "итог: $(row firewall), вызовы: $(calls)"

echo "[test] firewall: агент с IP панели — доступ только с панели, порт панели не трогается"
printf 'NODE_AGENT_PORT=9100\nNODE_AGENT_ALLOWED_IPS=203.0.113.10/32\n' >"$INSTALL/backend/node_agent.env"
UFW_ADDED="ufw deny 9100/tcp comment 'AdminPanelAZ node agent'" run 'fu_run firewall fu_step_firewall'
grep -qxF "ufw allow from 203.0.113.10 to any port 9100 proto tcp comment AdminPanelAZ node agent" "$CALLS" \
  && ok "allow с IP панели" || bad "вызовы: $(calls)"
grep -qxF "ufw deny 9100/tcp comment AdminPanelAZ node agent" "$CALLS" && ok "deny остальным" || bad "вызовы: $(calls)"
! grep -qE ' (8000|443|80)/tcp' "$CALLS" && ok "порты панели не трогаются" || bad "вызовы: $(calls)"
[[ "$(row firewall)" == "ok|ufw: правила AdminPanelAZ применены заново" ]] && ok "итог ok" || bad "итог: $(row firewall)"
rm -f "$INSTALL/backend/node_agent.env"

echo "[test] DDNS: нет ddns.env — пропущен"
rm -f "$TMP/ddns.env"
run 'fu_run ddns fu_step_ddns'
[[ "$(row ddns)" == "пропущен|не настроен" && "$(calls)" == "" ]] && ok "пропущен" || bad "итог: $(row ddns), вызовы: $(calls)"

# Без SYSTEMD_UNIT_DIR в ddns-update.sh install-timer писал бы в /etc/systemd/system хоста.
if grep -qF '"$UNIT_DIR/${SERVICE_NAME}.service"' "$ROOT_DIR/scripts/ddns-update.sh"; then
  echo "[test] DDNS: ddns.env есть — unit и таймер из systemd/ в SYSTEMD_UNIT_DIR, enable --now"
  printf 'DDNS_PROVIDER=duckdns\n' >"$TMP/ddns.env"
  run 'id() { echo 0; }; export -f id systemctl; fu_run ddns fu_step_ddns'
  [[ "$(calls)" == "systemctl daemon-reload;systemctl enable --now adminpanelaz-ddns.timer;" ]] && ok "daemon-reload, enable --now" \
    || bad "вызовы: $(calls); $(cat "$TMP/out")"
  grep -qxF "ExecStart=$ROOT_DIR/scripts/ddns-update.sh update" "$TMP/units/adminpanelaz-ddns.service" \
    && ok "unit — путь установки" || bad "unit: $(cat "$TMP/units/adminpanelaz-ddns.service" 2>&1)"
  cmp -s "$ROOT_DIR/systemd/adminpanelaz-ddns.timer" "$TMP/units/adminpanelaz-ddns.timer" && ok "таймер скопирован" \
    || bad "таймера нет в $TMP/units"
  [[ "$(row ddns)" == "ok|adminpanelaz-ddns.timer" ]] && ok "итог ok" || bad "итог: $(row ddns)"

  echo "[test] DDNS: install-timer с ошибкой — «ошибка» без стопа"
  run 'id() { echo 1000; }; export -f id; fu_run ddns fu_step_ddns; echo "stopped=$FU_STOPPED"'
  [[ "$(row ddns)" == "ошибка|ddns-update.sh install-timer не прошёл — см. вывод выше" ]] && grep -qx "stopped=false" "$TMP/out" \
    && ok "ошибка без стопа" || bad "итог: $(row ddns); $(cat "$TMP/out")"
else
  bad "ddns-update.sh пишет unit'ы мимо SYSTEMD_UNIT_DIR — тесты install-timer не запускались"
fi

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
