#!/usr/bin/env bash
# Вид меню: значки по исходной локали пользователя (UTF-8 — ✓ ! ✗ i, иначе [ok] [!] [x] [i]), обрезка по ширине
# терминала с многоточием, без цвета вне терминала и при NO_COLOR; снимки (golden) --status, главного меню и меню
# агента при NO_COLOR=1 и COLUMNS=80 / 60 с подменёнными пробами.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CALLS="$TMP/calls.log"
INSTALL="$TMP/install"
mkdir -p "$INSTALL/frontend" "$INSTALL/backend" "$TMP/units"
printf '{\n  "version": "2.26.4"\n}\n' >"$INSTALL/frontend/package.json"
printf '%s\n' DOMAIN=panel-with-a-long-name.example.com BEHIND_NGINX=true HTTPS_PUBLIC_PORT=8443 \
  ACCESS_PATH=/secret-path >"$INSTALL/backend/.env"

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

# render <COLUMNS> <код>: код с подключённым меню; git, systemctl, curl подменены (всё работает), без цвета,
# исходная локаль — RENDER_LANG (по умолчанию C.UTF-8). Вывод — в $TMP/out, код — в $rc.
render() {
  : >"$CALLS"
  set +e
  env -u LC_ALL -u LC_CTYPE LANG="${RENDER_LANG:-C.UTF-8}" NO_COLOR=1 COLUMNS="$1" INSTALL_DIR="$INSTALL" \
    SYSTEMD_UNIT_DIR="$TMP/units" bash -c '
    set -euo pipefail
    source "$1/scripts/adminpanel-menu.sh"
    git() { case "$*" in *rev-parse*) echo cef39ac ;; *symbolic-ref*) echo feature/console-menu-redesign ;; esac; }
    timeout() { shift; "$@"; }
    systemctl() { echo active; }
    curl() { return 0; }
    sleep() { :; }
    eval "$2"
  ' bash "$ROOT_DIR" "$2" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

# golden <название>: вывод в $TMP/out совпадает со снимком из stdin
golden() {
  local want
  want="$(cat)"
  if [[ "$(cat "$TMP/out")" == "$want" ]]; then
    ok "$1"
  else
    bad "$1"
    diff <(printf '%s\n' "$want") "$TMP/out" >&2 || true
  fi
}

# glyphs <переменные локали...>: значки ui_* и разделители при такой исходной локали
glyphs() {
  env -u LC_ALL -u LC_CTYPE -u LANG "$@" bash -c '
    source "$1/scripts/adminpanel-menu.sh"
    ui_ok a; ui_warn b 2>&1; ui_fail c 2>&1; ui_info d
    printf "%s|%s|%s\n" "$MENU_DOT" "$MENU_ELLIPSIS" "$LC_ALL"
  ' bash "$ROOT_DIR"
}
ASCII=$'  [ok]  a\n  [!]  b\n  [x]  c\n  [i]  d\n-|...|'
UTF8=$'  ✓  a\n  !  b\n  ✗  c\n  i  d\n·|…|'

echo "[test] значки по исходной локали, а не по C.UTF-8 самого скрипта"
[[ "$(glyphs LANG=C)" == "${ASCII}C.UTF-8" ]] && ok "LANG=C — ASCII" || bad "LANG=C: $(glyphs LANG=C)"
[[ "$(glyphs LC_ALL=POSIX)" == "${ASCII}POSIX" ]] && ok "LC_ALL=POSIX — ASCII" || bad "POSIX: $(glyphs LC_ALL=POSIX)"
[[ "$(glyphs)" == "${ASCII}C.UTF-8" ]] && ok "локаль не задана — ASCII" || bad "без локали: $(glyphs)"
[[ "$(glyphs LC_CTYPE=C LANG=en_US.UTF-8)" == "${ASCII}C.UTF-8" ]] && ok "LC_CTYPE=C важнее LANG" \
  || bad "LC_CTYPE: $(glyphs LC_CTYPE=C LANG=en_US.UTF-8)"
[[ "$(glyphs LANG=en_US.UTF-8)" == "${UTF8}C.UTF-8" ]] && ok "LANG=en_US.UTF-8 — Unicode" || bad "UTF-8: $(glyphs LANG=en_US.UTF-8)"
[[ "$(glyphs LC_ALL=C.utf8 LC_CTYPE=C)" == "${UTF8}C.utf8" ]] && ok "LC_ALL=C.utf8 важнее LC_CTYPE" \
  || bad "LC_ALL: $(glyphs LC_ALL=C.utf8 LC_CTYPE=C)"

echo "[test] ширина: COLUMNS, иначе tput cols, иначе 80; не меньше 40"
render 60 'menu_cols'
[[ "$(cat "$TMP/out")" == 60 ]] && ok "COLUMNS=60" || bad "60: $(cat "$TMP/out")"
render 30 'menu_cols'
[[ "$(cat "$TMP/out")" == 40 ]] && ok "COLUMNS=30 — 40" || bad "30: $(cat "$TMP/out")"
render x 'tput() { return 1; }; menu_cols'
[[ "$(cat "$TMP/out")" == 80 ]] && ok "без COLUMNS и tput — 80" || bad "80: $(cat "$TMP/out")"
render x 'tput() { echo 132; }; menu_cols'
[[ "$(cat "$TMP/out")" == 132 ]] && ok "tput cols" || bad "tput: $(cat "$TMP/out")"

echo "[test] обрезка с многоточием, по символам, а не байтам"
render 80 'menu_fit abcdef 6; echo; menu_fit abcdefg 6; echo; menu_fit "Проверка состояния" 9'
[[ "$(cat "$TMP/out")" == $'abcdef\nabcde…\nПроверка…' ]] && ok "abcdef / abcde… / Проверка…" || bad "вывод: $(cat "$TMP/out")"

echo "[test] golden: --status, панель и агент, 80 колонок"
with_units adminpanelaz.service adminpanelaz-node.service
render 80 'main --status'
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc"
golden "--status, 80" <<'EOF'
AdminPanelAZ 2.26.4 · feature/console-menu-redesign @ cef39ac
  Панель   работает · health отвечает
  Адрес    https://panel-with-a-long-name.example.com:8443/secret-path/
  Агент    работает (node)
EOF

echo "[test] golden: --status, 60 колонок — ветка@коммит и адрес обрезаны"
render 60 'main --status'
golden "--status, 60" <<'EOF'
AdminPanelAZ 2.26.4 · feature/console-menu-redesign @ cef39…
  Панель   работает · health отвечает
  Адрес    https://panel-with-a-long-name.example.com:8443/…
  Агент    работает (node)
EOF

echo "[test] golden: --status при исходной локали C — ASCII"
RENDER_LANG=C render 60 'main --status'
golden "--status, LANG=C, 60" <<'EOF'
AdminPanelAZ 2.26.4 - feature/console-menu-redesign @ cef...
  Панель   работает - health отвечает
  Адрес    https://panel-with-a-long-name.example.com:844...
  Агент    работает (node)
EOF

echo "[test] без NO_COLOR, но в pipe: нет \\033"
with_units adminpanelaz.service
set +e
env -u NO_COLOR -u LC_ALL -u LC_CTYPE LANG=C.UTF-8 TERM=xterm COLUMNS=80 INSTALL_DIR="$INSTALL" \
  SYSTEMD_UNIT_DIR="$TMP/units" bash -c '
  source "$1/scripts/adminpanel-menu.sh"
  timeout() { shift; "$@"; }
  systemctl() { echo failed; }
  curl() { return 1; }
  main --status
  ui_ok x; ui_fail y 2>&1
' bash "$ROOT_DIR" | cat >"$TMP/out"
set -e
grep -q "ошибка · health не отвечает" "$TMP/out" && ok "состояние словом" || bad "вывод: $(cat "$TMP/out")"
! grep -q $'\033' "$TMP/out" && ok "без escape-кодов" || bad "в pipe есть \\033"

echo "[test] приглашение: диапазон и q"
render 80 'menu_read 8 выход </dev/null; echo "choice=$MENU_CHOICE"'
[[ "$(cat "$TMP/out")" == $'Выберите [0-8, q — выход]: \nchoice=0' ]] && ok "конец ввода — 0" || bad "вывод: $(cat "$TMP/out")"
render 80 'menu_read 3 назад <<<q; echo "choice=$MENU_CHOICE"'
[[ "$(cat "$TMP/out")" == "Выберите [0-3, q — назад]: choice=0" ]] && ok "q — 0" || bad "вывод: $(cat "$TMP/out")"

echo "[test] golden: главное меню панели, 80 колонок"
with_units adminpanelaz.service
render 80 'menu_probe panel; menu_render_main panel'
golden "главное меню, 80" <<'EOF'
AdminPanelAZ 2.26.4 · feature/console-menu-redesign @ cef39ac
  Панель   работает · health отвечает
  Адрес    https://panel-with-a-long-name.example.com:8443/secret-path/

  1  Обновить и перезапустить
  2  Журнал
  3  Диагностика сайта
  4  Перезапустить панель
  5  Сервисы: nginx, агент, DDNS
  6  Бэкап и восстановление
  7  Сброс пароля / 2FA
  8  Аварийно: nginx, белый список IP

  0  Выход
EOF
! grep -q $'\033' "$TMP/out" && ok "NO_COLOR — без \\033" || bad "есть \\033"

echo "[test] golden: главное меню панели, 60 колонок"
render 60 'menu_probe panel; menu_render_main panel'
golden "главное меню, 60" <<'EOF'
AdminPanelAZ 2.26.4 · feature/console-menu-redesign @ cef39…
  Панель   работает · health отвечает
  Адрес    https://panel-with-a-long-name.example.com:8443/…

  1  Обновить и перезапустить
  2  Журнал
  3  Диагностика сайта
  4  Перезапустить панель
  5  Сервисы: nginx, агент, DDNS
  6  Бэкап и восстановление
  7  Сброс пароля / 2FA
  8  Аварийно: nginx, белый список IP

  0  Выход
EOF

echo "[test] пункты главного меню вызывают свои действия; 9 без агента — неверный выбор; q — выход"
STUBS='
  for fn in panel_update_interactive panel_diagnose panel_restart_and_wait panel_reset_password \
    menu_logs menu_services menu_backups menu_emergency menu_agent; do
    eval "$fn() { echo \"$fn \$*\" >>\"\$CALLS\"; }"
  done'
render 80 "$STUBS"'; main_menu panel <<<"$(printf "%s\n" 1 2 3 4 5 6 7 8 9 q)"'
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc"
[[ "$(tr '\n' ';' <"$CALLS")" == "panel_update_interactive ;menu_logs adminpanelaz;panel_diagnose ;panel_restart_and_wait ;menu_services ;menu_backups ;panel_reset_password ;menu_emergency ;" ]] \
  && ok "1–8" || bad "вызовы: $(tr '\n' ';' <"$CALLS")"
grep -q "Неверный выбор" "$TMP/out" && ok "9 — неверный выбор" || bad "вывод: $(cat "$TMP/out")"
grep -q "Проверка состояния…" "$TMP/out" && ok "строка проб перед шапкой" || bad "нет строки проб"

echo "[test] «Аварийно»: восстановить nginx, отключить белый список IP"
render 80 'panel_nginx_repair() { echo nginx_repair >>"$CALLS"; }; panel_disable_ip_whitelist() { echo whitelist >>"$CALLS"; }
  menu_emergency <<<"$(printf "%s\n" 1 2 0)"'
[[ "$(tr '\n' ';' <"$CALLS")" == "nginx_repair;whitelist;" ]] && ok "1, 2" || bad "вызовы: $(tr '\n' ';' <"$CALLS")"
grep -q "^Аварийно$" "$TMP/out" && ok "заголовок подменю — одна строка" || bad "вывод: $(cat "$TMP/out")"

echo "[test] прежних рамок и подменю нет"
! grep -nE '_m_(top|bot|sep|border|title|item)|menu_service_panel|menu_backups_updates|menu_diagnostics|panel_logs|──' \
  "$ROOT_DIR/scripts/adminpanel-menu.sh" && ok "нет _m_*, старых подменю и разделителей" || bad "остались прежние элементы"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
