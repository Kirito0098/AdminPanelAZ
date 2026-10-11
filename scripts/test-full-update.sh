#!/usr/bin/env bash
# Полное обновление (sudo ./install.sh --update, scripts/full-update.sh): итог по шагам и коды выхода, бэкап и код,
# порядок шагов на сервере с панелью и на сервере-узле, остановка, re-exec обновлённого install.sh, запуск
# и подтверждение, флаги install.sh, пункт меню. git, pip, npm, apt-get, dpkg, systemctl, ufw и curl подменены.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CALLS="$TMP/calls.log"
INSTALL="$TMP/install"
mkdir -p "$INSTALL/backend" "$INSTALL/scripts" "$TMP/units" "$TMP/venv/bin"
printf 'BACKEND_PORT=8000\nBACKEND_HOST=127.0.0.1\n' >"$INSTALL/backend/.env"
# pip, refresh-systemd-units.sh и install.sh установки — отдельные программы: только записывают вызов.
cat >"$TMP/venv/bin/pip" <<'EOF'
#!/usr/bin/env bash
echo "pip $*" >>"$CALLS"
[[ "${PIP_FAIL:-0}" != 1 ]]
EOF
cat >"$INSTALL/scripts/refresh-systemd-units.sh" <<'EOF'
#!/usr/bin/env bash
echo "refresh SYSTEMD_UNIT_DIR=$SYSTEMD_UNIT_DIR" >>"$CALLS"
EOF
cat >"$INSTALL/install.sh" <<'EOF'
#!/usr/bin/env bash
echo "install.sh $* LC_ALL=${LC_ALL-unset} LANG=${LANG-unset}" >>"$CALLS"
EOF
chmod +x "$TMP/venv/bin/pip"

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

# run <ввод> <код>: код в bash -c с подключённым scripts/full-update.sh; вывод — $TMP/out, код возврата — rc.
# LOCALE — исходная локаль (C.UTF-8), COLS — ширина (100). UPDATE_RESULT=same|changed|fail — итог panel_update,
# BACKUP_FAIL=1, NPM_FAIL=1, PIP_FAIL=1, CURL_OK=no — отказы; full_update_reexec продолжает в том же процессе,
# как продолжил бы новый install.sh (REAL_REEXEC=1 — настоящий).
run() {
  : >"$CALLS"
  rm -f "$CALLS.pulled"
  set +e
  printf '%b' "$1" | env -u LC_ALL -u LC_CTYPE -u SSH_CONNECTION LANG="${LOCALE:-C.UTF-8}" NO_COLOR=1 \
    COLUMNS="${COLS:-100}" TMPDIR="$TMP" INSTALL_DIR="$INSTALL" VENV_PATH="$TMP/venv" SYSTEMD_UNIT_DIR="$TMP/units" \
    DDNS_CONFIG="$TMP/ddns.env" bash -c '
    set -euo pipefail
    source "$1/scripts/full-update.sh"
    require_root() { :; }
    timeout() { shift; "$@"; }
    sleep() { echo "sleep $*" >>"$CALLS"; }
    systemctl() {
      case "$1" in
        is-active) echo "${STATE:-active}"; [[ "${STATE:-active}" == active ]] ;;
        *) echo "systemctl $*" >>"$CALLS" ;;
      esac
    }
    curl() { echo "curl" >>"$CALLS"; [[ "${CURL_OK:-yes}" == yes ]]; }
    git() {
      case "$*" in
        *"rev-parse --short HEAD") if [[ -f "$CALLS.pulled" ]]; then echo 1a2b3c4; else echo cef39ac; fi ;;
        *) echo "git $*" >>"$CALLS" ;;
      esac
    }
    panel_backup() {
      echo "backup $*" >>"$CALLS"
      [[ "${BACKUP_FAIL:-0}" != 1 ]] || return 1
      PANEL_LAST_BACKUP=/var/backups/adminpanelaz/adminpanelaz_20261011-1230.tar.gz
    }
    panel_update() {
      echo "update code_only=$PANEL_UPDATE_CODE_ONLY" >>"$CALLS"
      case "${UPDATE_RESULT:-same}" in
        changed) touch "$CALLS.pulled"; PANEL_UPDATE_CHANGED=true ;;
        fail) return 1 ;;
      esac
    }
    dpkg() { printf "Package: %s\nStatus: install ok installed\n" "$2"; }
    apt-get() { echo "apt-get $*" >>"$CALLS"; }
    panel_build_frontend() { echo "npm" >>"$CALLS"; [[ "${NPM_FAIL:-0}" != 1 ]]; }
    ufw() { case "$1" in show | status) : ;; *) echo "ufw $*" >>"$CALLS" ;; esac; }
    if [[ -z "${REAL_REEXEC:-}" ]]; then
      full_update_reexec() { echo "reexec" >>"$CALLS"; full_update_apply; fu_finish; exit "$FU_EXIT"; }
    fi
    eval "$2"
  ' bash "$ROOT_DIR" "$2" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

calls() { tr '\n' ';' <"$CALLS"; }
summary() { sed -n '/^Полное обновление$/,$p' "$TMP/out"; }
golden() {
  local expected
  expected="$(cat)"
  if [[ "$(summary)" == "$expected" ]]; then
    ok "$1"
  else
    bad "$1"
    diff <(printf '%s\n' "$expected") <(summary) >&2 || true
  fi
}

# Начало кода тестов итога: свой файл итога в TMPDIR.
INIT_STATE='FU_STATE="$TMPDIR/adminpanelaz-update.t"; : >"$FU_STATE"; '
ROWS='fu_row backup ok adminpanelaz_20261011-1230.tar.gz
  fu_row code ok "cef39ac $FU_ARROW 1a2b3c4"
  fu_row apt ok "доустановлено: 0"
  fu_row pip ok
  fu_row frontend ok
  fu_row systemd ok "adminpanelaz, adminpanelaz-node"
  fu_row nginx ошибка "старый конфиг восстановлен (nginx -t: [emerg] unknown directive)"
  fu_row firewall пропущен "не настроен"
  fu_row ddns пропущен "не настроен"
  fu_row restart ok "панель отвечает"
'

echo "[test] итог: слово-статус, колонки по символам, без цвета; «ошибка» — код 1, файл итога удалён"
with_units adminpanelaz.service
run '' "$INIT_STATE$ROWS"'fu_finish; exit "$FU_EXIT"'
golden "итог, 100 колонок" <<'EOF'
Полное обновление
  Бэкап      ok        adminpanelaz_20261011-1230.tar.gz
  Код        ok        cef39ac → 1a2b3c4
  Пакеты     ok        доустановлено: 0
  Python     ok
  Интерфейс  ok
  systemd    ok        adminpanelaz, adminpanelaz-node
  nginx      ошибка    старый конфиг восстановлен (nginx -t: [emerg] unknown directive)
  firewall   пропущен  не настроен
  DDNS       пропущен  не настроен
  Перезапуск ok        панель отвечает
EOF
[[ "$rc" -eq 1 ]] && ok "код 1" || bad "код $rc: $(cat "$TMP/out")"
[[ ! -e "$TMP/adminpanelaz-update.t" ]] && ok "файл итога удалён" || bad "файл итога остался"
! grep -q $'\033' "$TMP/out" && ok "NO_COLOR — без \\033" || bad "есть \\033"

echo "[test] итог в 60 колонок: длинные подробности обрезаются с …"
COLS=60 run '' "$INIT_STATE$ROWS"'fu_finish'
grep -qxF "  nginx      ошибка    старый конфиг восстановлен (nginx -t…" "$TMP/out" && ok "обрезка по ширине" \
  || bad "итог: $(summary)"

echo "[test] локаль не UTF-8: стрелка ->; шаги без строки — «пропущен  не выполнялся», код 0"
LOCALE=C run '' "$INIT_STATE"'fu_row code ok "cef39ac $FU_ARROW 1a2b3c4"; fu_finish; exit "$FU_EXIT"'
grep -qxF "  Код        ok        cef39ac -> 1a2b3c4" "$TMP/out" && ! grep -q "→" "$TMP/out" && ok "ASCII-стрелка" \
  || bad "итог: $(summary)"
grep -qxF "  Бэкап      пропущен  не выполнялся" "$TMP/out" && ok "не выполнялся" || bad "итог: $(summary)"
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc"

echo "[test] панель не ответила: имя бэкапа и как восстановить"
run '' "$INIT_STATE"'fu_row backup ok adminpanelaz_20261011-1230.tar.gz
  fu_row restart ошибка "панель не ответила за 30 с"; fu_finish; exit "$FU_EXIT"'
[[ "$rc" -eq 1 ]] && ok "код 1" || bad "код $rc"
grep -qF "Бэкап до обновления: adminpanelaz_20261011-1230.tar.gz" "$TMP/out" \
  && grep -qF "Восстановить: sudo adminpanelaz → 6 Бэкап и восстановление" "$TMP/out" && ok "подсказка" \
  || bad "вывод: $(cat "$TMP/out")"

STEPS='step_fail() { false; echo "after false" >>"$CALLS"; }
  step_ok() { echo "step_ok" >>"$CALLS"; }
'
echo "[test] шаг идёт с set -e; ошибка шага-стопа (pip) останавливает следующие шаги"
run '' "$INIT_STATE$STEPS"'fu_run pip step_fail; fu_run systemd step_ok; echo "stopped=$FU_STOPPED"; cat "$FU_STATE"'
[[ "$(calls)" == "" ]] && ok "после false шаг прерван, следующий не запущен" || bad "вызовы: $(calls)"
grep -qx "stopped=true" "$TMP/out" && ok "остановлено" || bad "вывод: $(cat "$TMP/out")"
grep -qxF $'pip\tошибка\tpip install не прошёл — панель не перезапускалась' "$TMP/out" && ok "строка итога pip" \
  || bad "вывод: $(cat "$TMP/out")"

echo "[test] ошибка шага без остановки (nginx): «ошибка», следующие шаги выполняются"
run '' "$INIT_STATE$STEPS"'fu_run nginx step_fail; fu_run systemd step_ok; echo "stopped=$FU_STOPPED"; cat "$FU_STATE"'
[[ "$(calls)" == "step_ok;" ]] && ok "следующий шаг выполнен" || bad "вызовы: $(calls)"
grep -qx "stopped=false" "$TMP/out" && ok "не остановлено" || bad "вывод: $(cat "$TMP/out")"
grep -qxF $'nginx\tошибка\tнепредвиденная ошибка (код 1), см. вывод выше' "$TMP/out" \
  && grep -qxF $'systemd\tok\t' "$TMP/out" && ok "строки итога" || bad "вывод: $(cat "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
