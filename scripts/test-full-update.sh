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
# как продолжил бы новый install.sh (REAL_REEXEC=1 — настоящий). STATE_UID — ожидаемый владелец файла --resume
# (по умолчанию тот, кто запускает тест; в работе — root).
run() {
  : >"$CALLS"
  rm -f "$CALLS.pulled"
  set +e
  printf '%b' "$1" | env -u LC_ALL -u LC_CTYPE -u SSH_CONNECTION LANG="${LOCALE:-C.UTF-8}" NO_COLOR=1 \
    COLUMNS="${COLS:-100}" TMPDIR="$TMP" INSTALL_DIR="$INSTALL" VENV_PATH="$TMP/venv" SYSTEMD_UNIT_DIR="$TMP/units" \
    DDNS_CONFIG="$TMP/ddns.env" ADMINPANELAZ_TEST_STATE_UID="${STATE_UID:-$(id -u)}" bash -c '
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

echo "[test] бэкап и код на сервере с панелью: create --no-prune --keep-running, затем только git"
with_units adminpanelaz.service
run '' "$INIT_STATE"'fu_run backup fu_step_backup; fu_run code fu_step_code; cat "$FU_STATE"'
[[ "$(calls)" == "backup --no-prune --keep-running;update code_only=true;" ]] && ok "бэкап, затем код" \
  || bad "вызовы: $(calls)"
grep -qxF $'backup\tok\tadminpanelaz_20261011-1230.tar.gz' "$TMP/out" && ok "имя архива" || bad "вывод: $(cat "$TMP/out")"
grep -qxF $'code\tok\tактуально, cef39ac' "$TMP/out" && ok "код актуален" || bad "вывод: $(cat "$TMP/out")"

echo "[test] код обновился: «до → после»"
UPDATE_RESULT=changed run '' "$INIT_STATE"'fu_run backup fu_step_backup; fu_run code fu_step_code; cat "$FU_STATE"'
grep -qxF $'code\tok\tcef39ac → 1a2b3c4' "$TMP/out" && ok "cef39ac → 1a2b3c4" || bad "вывод: $(cat "$TMP/out")"

echo "[test] сервер-узел: бэкапа нет, код обновляется"
with_units adminpanelaz-node.service
run '' "$INIT_STATE"'fu_run backup fu_step_backup; fu_run code fu_step_code; cat "$FU_STATE"'
[[ "$(calls)" == "update code_only=true;" ]] && ok "только код" || bad "вызовы: $(calls)"
grep -qxF $'backup\tпропущен\tнет панели' "$TMP/out" && ok "бэкап пропущен" || bad "вывод: $(cat "$TMP/out")"

echo "[test] бэкап не создан: стоп до обновления кода"
with_units adminpanelaz.service
BACKUP_FAIL=1 run '' "$INIT_STATE"'fu_run backup fu_step_backup; fu_run code fu_step_code; echo "stopped=$FU_STOPPED"; cat "$FU_STATE"'
[[ "$(calls)" == "backup --no-prune --keep-running;" ]] && ok "код не трогали" || bad "вызовы: $(calls)"
grep -qx "stopped=true" "$TMP/out" && grep -qxF $'backup\tошибка\tбэкап не создан — обновление не начиналось' "$TMP/out" \
  && ok "стоп с причиной" || bad "вывод: $(cat "$TMP/out")"

echo "[test] код не обновился: стоп"
UPDATE_RESULT=fail run '' "$INIT_STATE"'fu_run backup fu_step_backup; fu_run code fu_step_code; echo "stopped=$FU_STOPPED"; cat "$FU_STATE"'
grep -qx "stopped=true" "$TMP/out" && grep -qxF $'code\tошибка\tкод не обновлён — подробности выше' "$TMP/out" \
  && ok "стоп с причиной" || bad "вывод: $(cat "$TMP/out")"

echo "[test] re-exec: обновлённый install.sh с --update -y --update-resume=<итог> и исходной локалью"
REAL_REEXEC=1 run '' 'FU_STATE="$TMPDIR/adminpanelaz-update.abc"; full_update_reexec; echo "not reached" >>"$CALLS"'
[[ "$(calls)" == "install.sh --update -y --update-resume=$TMP/adminpanelaz-update.abc LC_ALL= LANG=C.UTF-8;" ]] \
  && ok "exec install.sh" || bad "вызовы: $(calls); вывод: $(cat "$TMP/out")"

echo "[test] сервер с панелью: бэкап → код → apt → pip → интерфейс → unit'ы → … → перезапуск и health"
with_units adminpanelaz.service
rm -f "$TMP"/adminpanelaz-update.*
run '' 'full_update_main --yes'
[[ "$(calls)" == "backup --no-prune --keep-running;update code_only=true;pip install -q -r $INSTALL/backend/requirements.txt;npm;refresh SYSTEMD_UNIT_DIR=$TMP/units;systemctl restart adminpanelaz;curl;" ]] \
  && ok "порядок шагов" || bad "вызовы: $(calls)"
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out")"
golden "итог на сервере с панелью" <<'EOF'
Полное обновление
  Бэкап      ok        adminpanelaz_20261011-1230.tar.gz
  Код        ok        актуально, cef39ac
  Пакеты     ok        доустановлено: 0
  Python     ok
  Интерфейс  ok
  systemd    ok        adminpanelaz
  nginx      пропущен  публикация без nginx
  firewall   пропущен  не настроен
  DDNS       пропущен  не настроен
  Перезапуск ok        панель отвечает
EOF
[[ -z "$(find "$TMP" -maxdepth 1 -name 'adminpanelaz-update.*')" ]] && ok "файл итога удалён" \
  || bad "остался: $(find "$TMP" -maxdepth 1 -name 'adminpanelaz-update.*')"

echo "[test] сервер-узел: без бэкапа, интерфейса и nginx; агент перезапущен и проверен через 5 с"
with_units adminpanelaz-node.service
run '' 'full_update_main --yes'
[[ "$(calls)" == "update code_only=true;pip install -q -r $INSTALL/backend/requirements.txt;refresh SYSTEMD_UNIT_DIR=$TMP/units;systemctl restart adminpanelaz-node;sleep 5;" ]] \
  && ok "шаги агента" || bad "вызовы: $(calls)"
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out")"
golden "итог на сервере-узле" <<'EOF'
Полное обновление
  Бэкап      пропущен  нет панели
  Код        ok        актуально, cef39ac
  Пакеты     ok        доустановлено: 0
  Python     ok
  Интерфейс  пропущен  нет панели
  systemd    ok        adminpanelaz-node
  nginx      пропущен  нет панели
  firewall   пропущен  не настроен
  DDNS       пропущен  не настроен
  Перезапуск ok        adminpanelaz-node работает
EOF

echo "[test] код обновился: остальные шаги — после re-exec обновлённого install.sh"
with_units adminpanelaz.service
UPDATE_RESULT=changed run '' 'full_update_main --yes'
[[ "$(calls)" == "backup --no-prune --keep-running;update code_only=true;reexec;pip install -q -r $INSTALL/backend/requirements.txt;npm;refresh SYSTEMD_UNIT_DIR=$TMP/units;systemctl restart adminpanelaz;curl;" ]] \
  && ok "re-exec сразу после кода" || bad "вызовы: $(calls)"
grep -qxF "  Код        ok        cef39ac → 1a2b3c4" "$TMP/out" && ok "строка «Код»" || bad "итог: $(summary)"
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc"

echo "[test] pip с ошибкой: стоп — нет сборки, unit'ов, nginx и перезапуска"
PIP_FAIL=1 run '' 'fu_step_nginx() { echo "nginx-step" >>"$CALLS"; }; full_update_main --yes'
[[ "$(calls)" == "backup --no-prune --keep-running;update code_only=true;pip install -q -r $INSTALL/backend/requirements.txt;" ]] \
  && ok "после pip ничего" || bad "вызовы: $(calls)"
[[ "$rc" -eq 1 ]] && ok "код 1" || bad "код $rc"
grep -qxF "  Python     ошибка    pip install не прошёл — панель не перезапускалась" "$TMP/out" && ok "строка «Python»" \
  || bad "итог: $(summary)"
grep -qxF "  Перезапуск пропущен  не выполнялся" "$TMP/out" && ok "перезапуска не было" || bad "итог: $(summary)"

echo "[test] бэкап с ошибкой: стоп до кода"
BACKUP_FAIL=1 run '' 'full_update_main --yes'
[[ "$(calls)" == "backup --no-prune --keep-running;" ]] && ok "только бэкап" || bad "вызовы: $(calls)"
[[ "$rc" -eq 1 ]] && ok "код 1" || bad "код $rc"
grep -qxF "  Код        пропущен  не выполнялся" "$TMP/out" && ok "код не обновлялся" || bad "итог: $(summary)"

echo "[test] код с ошибкой: стоп"
UPDATE_RESULT=fail run '' 'full_update_main --yes'
[[ "$(calls)" == "backup --no-prune --keep-running;update code_only=true;" ]] && ok "после кода ничего" || bad "вызовы: $(calls)"
[[ "$rc" -eq 1 ]] && ok "код 1" || bad "код $rc"

echo "[test] панель не ответила: «ошибка», бэкап и как восстановить"
CURL_OK=no run '' 'full_update_main --yes'
[[ "$rc" -eq 1 ]] && ok "код 1" || bad "код $rc"
grep -qxF "  Перезапуск ошибка    панель не ответила за 30 с" "$TMP/out" && ok "строка «Перезапуск»" || bad "итог: $(summary)"
grep -qF "Бэкап до обновления: adminpanelaz_20261011-1230.tar.gz" "$TMP/out" && ok "имя бэкапа" || bad "вывод: $(cat "$TMP/out")"

echo "[test] локаль не UTF-8: значки и стрелка ASCII"
LOCALE=C UPDATE_RESULT=changed run '' 'full_update_main --yes'
grep -qxF "  Код        ok        cef39ac -> 1a2b3c4" "$TMP/out" && ok "стрелка ->" || bad "итог: $(summary)"
grep -qF "  [ok]  Все пакеты apt на месте" "$TMP/out" && ok "значок [ok]" || bad "вывод: $(cat "$TMP/out")"

echo "[test] ничего не установлено — код 1"
with_units
run '' 'full_update_main --yes'
[[ "$rc" -eq 1 && "$(calls)" == "" ]] && grep -qF "AdminPanelAZ не установлена: используйте обычную установку" "$TMP/out" \
  && ok "не установлена" || bad "код $rc: $(cat "$TMP/out")"

echo "[test] без терминала и без -y — код 2 с подсказкой"
with_units adminpanelaz.service
run '' 'full_update_main'
[[ "$rc" -eq 2 && "$(calls)" == "" ]] && grep -qF "Без вопросов: sudo ./install.sh --update -y" "$TMP/out" \
  && ok "код 2" || bad "код $rc: $(cat "$TMP/out")"

echo "[test] подтверждение: план, «Продолжить? [y/N]»; n и EOF — ничего не меняется, код 0; y — обновление"
run 'n\n' 'fu_stdin_is_tty() { :; }; full_update_main'
[[ "$rc" -eq 0 && "$(calls)" == "" ]] && grep -qF "Полное обновление отменено, ничего не изменено" "$TMP/out" \
  && ok "n — отмена" || bad "код $rc, вызовы: $(calls); $(cat "$TMP/out")"
grep -qF "Не меняются: база, backend/.env, *_agent.env, сертификаты, mTLS" "$TMP/out" \
  && grep -qF "Продолжить? [y/N]:" "$TMP/out" && ok "план и вопрос" || bad "вывод: $(cat "$TMP/out")"
run '' 'fu_stdin_is_tty() { :; }; full_update_main'
[[ "$rc" -eq 0 && "$(calls)" == "" ]] && ok "EOF — отмена" || bad "код $rc, вызовы: $(calls)"
run 'y\n' 'fu_stdin_is_tty() { :; }; full_update_main'
[[ "$rc" -eq 0 && "$(calls)" == "backup --no-prune --keep-running;"* ]] && ok "y — обновление" \
  || bad "код $rc, вызовы: $(calls)"

echo "[test] неизвестный аргумент — код 2"
run '' 'full_update_main --bogus'
[[ "$rc" -eq 2 ]] && grep -qF "Неизвестный аргумент: --bogus" "$TMP/out" && ok "код 2" || bad "код $rc: $(cat "$TMP/out")"

# state_file <имя> <содержимое printf>: файл итога этапа 1 в TMPDIR, права 600
state_file() {
  rm -f "$TMP/$1"
  printf "$2" >"$TMP/$1"
  chmod 600 "$TMP/$1"
}
STAGE1='backup\tok\tadminpanelaz_20261011-1230.tar.gz\ncode\tok\tcef39ac → 1a2b3c4\n'

# resume_rejected <описание> <путь>: --resume отклонён с кодом 2, шаги не запускались
resume_rejected() {
  run '' "full_update_main --yes --resume '$2'"
  [[ "$rc" -eq 2 && "$(calls)" == "" ]] && grep -qF "Неверный файл итога обновления" "$TMP/out" && ok "отказ: $1" \
    || bad "$1: код $rc, вызовы: $(calls); $(cat "$TMP/out")"
}

echo "[test] --resume: только файл adminpanelaz-update.* в TMPDIR, обычный, не symlink"
state_file target "$STAGE1"
ln -sf "$TMP/target" "$TMP/adminpanelaz-update.link"
resume_rejected "чужой путь" /etc/passwd
resume_rejected "symlink" "$TMP/adminpanelaz-update.link"
resume_rejected "нет файла" "$TMP/adminpanelaz-update.none"
mkdir -p "$TMP/sub"
state_file sub/adminpanelaz-update.n "$STAGE1"
resume_rejected "подкаталог TMPDIR" "$TMP/sub/adminpanelaz-update.n"
resume_rejected "путь с .." "$TMP/sub/../adminpanelaz-update.link"
mkdir "$TMP/adminpanelaz-update.d"
resume_rejected "каталог" "$TMP/adminpanelaz-update.d"
rm -rf "$TMP/adminpanelaz-update.link" "$TMP/target" "$TMP/sub" "$TMP/adminpanelaz-update.d"

echo "[test] --resume: файл не root (другой владелец) — отказ, файл не тронут"
state_file adminpanelaz-update.o "$STAGE1"
STATE_UID="$(($(id -u) + 1))" resume_rejected "владелец не тот" "$TMP/adminpanelaz-update.o"
[[ -f "$TMP/adminpanelaz-update.o" ]] && ok "чужой файл не удалён" || bad "чужой файл удалён"
rm -f "$TMP/adminpanelaz-update.o"
grep -qE 'ADMINPANELAZ_TEST_STATE_UID:-0\}' "$ROOT_DIR/scripts/full-update.sh" && ok "по умолчанию владелец — root (uid 0)" \
  || bad "владелец по умолчанию не uid 0"

echo "[test] --resume: файл доступен на запись группе или всем — отказ"
for mode in 620 602 666; do
  state_file adminpanelaz-update.w "$STAGE1"
  chmod "$mode" "$TMP/adminpanelaz-update.w"
  resume_rejected "права $mode" "$TMP/adminpanelaz-update.w"
done
rm -f "$TMP/adminpanelaz-update.w"

echo "[test] --resume: содержимое разбирается строго, ничего не исполняется"
for bad_rows in \
  'code\tok\tcef39ac\n$(touch "$TMPDIR/PWNED")\n' \
  'nginx\tok\t\ncode\tok\tcef39ac\n' \
  'backup\tok\tx\n' \
  'code\tошибка\tкод не обновлён\n' \
  'backup\tошибка\tx\ncode\tok\tcef39ac\n' \
  'code\tok\tcef39ac\ncode\tok\tcef39ac\n' \
  'code\tok\tcef39ac\textra\n' \
  'code\t\tok\n' \
  'code\tok\tcef\033[31mred\n' \
  'code ok cef39ac\n'; do
  state_file adminpanelaz-update.m "$bad_rows"
  resume_rejected "строки: $bad_rows" "$TMP/adminpanelaz-update.m"
done
state_file adminpanelaz-update.m "code\tok\t$(printf 'x%.0s' {1..5000})\n"
resume_rejected "больше 4 КБ" "$TMP/adminpanelaz-update.m"
[[ ! -e "$TMP/PWNED" ]] && ok "подстановка не выполнялась" || bad "команда из файла выполнена"
rm -f "$TMP/adminpanelaz-update.m"

echo "[test] этап 1: файл итога — mktemp в TMPDIR, права 600, владелец — запустивший (root)"
UPDATE_RESULT=changed run '' 'full_update_reexec() { stat -c "%a %u %n" "$FU_STATE" >"$TMPDIR/state-meta"; exit 0; }
  full_update_main --yes'
read -r st_mode st_uid st_name <"$TMP/state-meta" || true
[[ "$st_mode" == 600 && "$st_uid" == "$(id -u)" && "$st_name" =~ ^$TMP/adminpanelaz-update\.[A-Za-z0-9]{6}$ ]] \
  && ok "600, $st_name" || bad "файл итога: $(cat "$TMP/state-meta" 2>&1)"
rm -f "$TMP"/adminpanelaz-update.* "$TMP/state-meta"

echo "[test] --resume: шаги после кода, строки бэкапа и кода — из файла"
state_file adminpanelaz-update.r "$STAGE1"
run '' 'full_update_main --yes --resume "$TMPDIR/adminpanelaz-update.r"'
[[ "$(calls)" == "pip install -q -r $INSTALL/backend/requirements.txt;npm;refresh SYSTEMD_UNIT_DIR=$TMP/units;systemctl restart adminpanelaz;curl;" ]] \
  && ok "с шага «Пакеты»" || bad "вызовы: $(calls)"
grep -qxF "  Код        ok        cef39ac → 1a2b3c4" "$TMP/out" \
  && grep -qxF "  Бэкап      ok        adminpanelaz_20261011-1230.tar.gz" "$TMP/out" && ok "строки этапа 1" || bad "итог: $(summary)"
[[ -z "$(find "$TMP" -maxdepth 1 -name 'adminpanelaz-update.*')" ]] && ok "файлы итога удалены" \
  || bad "остались: $(find "$TMP" -maxdepth 1 -name 'adminpanelaz-update.*')"
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out")"
state_file adminpanelaz-update.r 'backup\tпропущен\tнет панели\ncode\tok\tактуально, cef39ac\n'
run '' 'full_update_main --yes --resume "$TMPDIR/adminpanelaz-update.r"'
[[ "$rc" -eq 0 ]] && grep -qxF "  Бэкап      пропущен  нет панели" "$TMP/out" && ok "бэкап «пропущен» на узле" \
  || bad "код $rc: $(summary)"

extract() {
  local file="$1" fn
  shift
  for fn in "$@"; do
    sed -n "/^${fn}() {/,/^}/p" "$file"
  done
}

# install_main <аргументы>: main из install.sh, шаги подменены и записывают своё имя; die — «DIE: …», код 1
install_main() {
  : >"$CALLS"
  set +e
  bash -c '
    set -euo pipefail
    WITH_DAEMON=false WITH_SYSTEMD=false WITH_NODE_AGENT=false NODE_ONLY=false PROXY_ONLY=false FORCE=false
    NON_INTERACTIVE=false ACCEPT_DEFAULTS=false ACTION=install PURGE_REPO=false
    UPDATE_REQUESTED=false UPDATE_RESUME_STATE=""
    eval "$1"
    shift
    stub() { echo "${FUNCNAME[1]}" >>"$CALLS"; }
    die() { echo "DIE: $*"; exit 1; }
    usage() { :; }
    require_root() { stub; }
    install_set_step() { stub; }
    check_reboot_required() { stub; }
    run_uninstall_action() { stub; }
    run_full_purge_action() { stub; }
    run_reinstall_action() { stub; }
    require_tty_or_explicit_intent() { stub; }
    show_main_menu() { stub; }
    run_install_flow() { stub; }
    run_update_action() { stub; exit 0; }
    main "$@"
  ' bash "$(extract "$ROOT_DIR/install.sh" parse_args validate_install_flags main)" "$@" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

echo "[test] install.sh --update -y и --update-resume=: сразу полное обновление, без reboot-проверки и мастера"
install_main --update -y
[[ "$rc" -eq 0 && "$(calls)" == "require_root;run_update_action;" ]] && ok "--update -y" || bad "код $rc, вызовы: $(calls)"
install_main --update -y --update-resume="$TMP/adminpanelaz-update.x"
[[ "$rc" -eq 0 && "$(calls)" == "require_root;run_update_action;" ]] && ok "--update-resume=" || bad "код $rc, вызовы: $(calls)"

echo "[test] install.sh --update несовместим с действиями и ролями"
for flag in --reinstall --uninstall --purge --purge-all --node-only --proxy-only --with-node-agent; do
  install_main --update "$flag"
  [[ "$rc" -eq 1 && "$(calls)" == "" ]] && grep -qF "DIE: --update несовместим с" "$TMP/out" && ok "--update $flag" \
    || bad "--update $flag: код $rc, вызовы: $(calls); $(cat "$TMP/out")"
done

echo "[test] install.sh --reinstall не изменился"
install_main --reinstall
[[ "$(calls)" == "require_root;install_set_step;check_reboot_required;run_reinstall_action;" ]] && ok "--reinstall" \
  || bad "вызовы: $(calls)"

mkdir -p "$TMP/repo/scripts"
cat >"$TMP/repo/scripts/full-update.sh" <<'EOF'
echo "full-update.sh $* INSTALL_DIR=$INSTALL_DIR" >>"$CALLS"
EOF
# update_action <ACCEPT_DEFAULTS> <NON_INTERACTIVE> <UPDATE_RESUME_STATE>
update_action() {
  : >"$CALLS"
  ROOT_DIR="$TMP/repo" bash -c '
    set -euo pipefail
    eval "$1"
    ACCEPT_DEFAULTS="$2" NON_INTERACTIVE="$3" UPDATE_RESUME_STATE="$4"
    run_update_action
    echo "not reached" >>"$CALLS"
  ' bash "$(extract "$ROOT_DIR/install.sh" run_update_action)" "$@" >"$TMP/out" 2>&1 || true
}

echo "[test] run_update_action: exec scripts/full-update.sh из каталога установки, --yes при -y/--non-interactive"
update_action false false ""
[[ "$(calls)" == "full-update.sh  INSTALL_DIR=$TMP/repo;" ]] && ok "без --yes" || bad "вызовы: $(calls); $(cat "$TMP/out")"
update_action true false ""
[[ "$(calls)" == "full-update.sh --yes INSTALL_DIR=$TMP/repo;" ]] && ok "-y → --yes" || bad "вызовы: $(calls)"
update_action false true ""
[[ "$(calls)" == "full-update.sh --yes INSTALL_DIR=$TMP/repo;" ]] && ok "--non-interactive → --yes" || bad "вызовы: $(calls)"
update_action true false "$TMP/adminpanelaz-update.s"
[[ "$(calls)" == "full-update.sh --yes --resume $TMP/adminpanelaz-update.s INSTALL_DIR=$TMP/repo;" ]] && ok "--resume" \
  || bad "вызовы: $(calls)"

echo "[test] --update в справке и в шапке install.sh"
grep -qE '^  --update +Полное обновление' "$ROOT_DIR/scripts/install-ui.sh" \
  && grep -qE '^#   --update +полное обновление' "$ROOT_DIR/install.sh" && ok "справка" || bad "--update нет в справке"

echo "[test] меню: «Полное обновление» спрашивает [y/N]; n и конец ввода — ничего; y — install.sh --update -y"
with_units adminpanelaz.service
run 'n\n' 'menu_full_update'
[[ "$(calls)" == "" ]] && grep -qF "Запустить полное обновление? [y/N]:" "$TMP/out" && ok "n — отмена" \
  || bad "вызовы: $(calls); $(cat "$TMP/out")"
run '' 'menu_full_update'
[[ "$(calls)" == "" ]] && ok "конец ввода — отмена" || bad "вызовы: $(calls)"
run 'y\n' 'menu_full_update'
[[ "$(calls)" == "install.sh --update -y LC_ALL= LANG=C.UTF-8;" ]] && ok "y — install.sh --update -y в исходной локали" \
  || bad "вызовы: $(calls); $(cat "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
