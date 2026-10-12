#!/usr/bin/env bash
# Шаг nginx полного обновления: свои vhost панели и портала пересобираются по .env с сертификатами из
# действующего файла, старый файл — рядом как <имя>.bak-ГГГГММДД-ЧЧММСС; nginx -t с ошибкой — старый файл
# возвращается, итог «ошибка», nginx не перезагружается. Каталоги nginx — во временном каталоге; nginx,
# systemctl, git, pip, npm, apt-get и curl подменены.
# shellcheck disable=SC2016
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CALLS="$TMP/calls.log"
INSTALL="$TMP/install"
NG="$TMP/nginx"
SA="$NG/sites-available"
mkdir -p "$INSTALL/backend" "$INSTALL/scripts" "$TMP/units" "$TMP/venv/bin"
cat >"$TMP/venv/bin/pip" <<'EOF'
#!/usr/bin/env bash
echo "pip $*" >>"$CALLS"
EOF
cat >"$INSTALL/scripts/refresh-systemd-units.sh" <<'EOF'
#!/usr/bin/env bash
echo "refresh SYSTEMD_UNIT_DIR=$SYSTEMD_UNIT_DIR" >>"$CALLS"
EOF
chmod +x "$TMP/venv/bin/pip"
NGINX_ENV='DOMAIN=panel.example.com
PORTAL_DOMAIN=portal.example.com
PUBLISH_MODE=nginx_le
BEHIND_NGINX=true
BACKEND_PORT=8000
HTTPS_PUBLIC_PORT=443
HTTP_ACME_PORT=80
ACCESS_PATH=/secret-path'

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

# old_vhost <файл> <хост>: vhost панели до обновления с сертификатом Let's Encrypt; копия — $TMP/<имя>.orig
old_vhost() {
  cat >"$1" <<EOF
# AdminPanelAZ — vhost до обновления
server {
    listen 443 ssl;
    server_name $2;
    ssl_certificate /etc/letsencrypt/live/$2/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$2/privkey.pem;
    location / { proxy_pass http://127.0.0.1:8000; }
}
EOF
  cp -a "$1" "$TMP/$(basename "$1").orig"
}

# reset_nginx [.env]: свои vhost панели и портала (симлинки в sites-enabled), .env, только unit панели
reset_nginx() {
  rm -rf "$NG" "$TMP/nginx-fail"
  mkdir -p "$SA" "$NG/sites-enabled" "$NG/snippets" "$NG/conf.d" "$NG/backups"
  printf '%s\n' "${1:-$NGINX_ENV}" >"$INSTALL/backend/.env"
  cp "$INSTALL/backend/.env" "$TMP/env.orig"
  old_vhost "$SA/panel_example_com" panel.example.com
  old_vhost "$SA/portal_example_com" portal.example.com
  ln -s ../sites-available/panel_example_com "$NG/sites-enabled/panel_example_com"
  ln -s ../sites-available/portal_example_com "$NG/sites-enabled/portal_example_com"
  with_units adminpanelaz.service
}

# run <код>: код в bash -c с подключённым scripts/full-update.sh; строки итога — $TMP/state (для отдельного
# шага, см. row), вывод — $TMP/out. Файл $TMP/nginx-fail — следующий nginx -t завершится ошибкой (один раз).
run() {
  : >"$CALLS"
  : >"$TMP/state"
  set +e
  env -u LC_ALL -u LC_CTYPE -u SSH_CONNECTION LANG=C.UTF-8 NO_COLOR=1 COLUMNS=200 TMPDIR="$TMP" \
    INSTALL_DIR="$INSTALL" VENV_PATH="$TMP/venv" SYSTEMD_UNIT_DIR="$TMP/units" DDNS_CONFIG="$TMP/ddns.env" \
    NGINX_SITES_AVAILABLE_DIR="$SA" NGINX_SITES_ENABLED_DIR="$NG/sites-enabled" NGINX_SNIPPETS_DIR="$NG/snippets" \
    NGINX_CONF_D_DIR="$NG/conf.d" NGINX_BACKUPS_DIR="$NG/backups" NGINX_FAIL_ONCE="$TMP/nginx-fail" \
    FU_TEST_STATE="$TMP/state" bash -c '
    set -euo pipefail
    source "$1/scripts/full-update.sh"
    FU_STATE="$FU_TEST_STATE"
    require_root() { :; }
    timeout() { shift; "$@"; }
    sleep() { echo "sleep $*" >>"$CALLS"; }
    nginx() {
      echo "nginx $*" >>"$CALLS"
      if [[ -f "$NGINX_FAIL_ONCE" ]]; then
        rm -f "$NGINX_FAIL_ONCE"
        echo "nginx: [emerg] unknown directive \"foo\" in /etc/nginx/sites-enabled/panel_example_com:30" >&2
        echo "nginx: configuration file /etc/nginx/nginx.conf test failed" >&2
        return 1
      fi
    }
    systemctl() {
      case "$1" in
        is-active) echo active ;;
        *) echo "systemctl $*" >>"$CALLS" ;;
      esac
    }
    curl() { echo "curl" >>"$CALLS"; }
    git() { echo cef39ac; }
    panel_backup() {
      echo "backup $*" >>"$CALLS"
      PANEL_LAST_BACKUP=/var/backups/adminpanelaz/adminpanelaz_20261011-1230.tar.gz
    }
    panel_update() { echo "update" >>"$CALLS"; }
    dpkg() { printf "Package: %s\nStatus: install ok installed\n" "$2"; }
    apt-get() { echo "apt-get $*" >>"$CALLS"; }
    panel_build_frontend() { echo "npm" >>"$CALLS"; }
    ufw() { :; }
    eval "$2"
  ' bash "$ROOT_DIR" "$1" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

calls() { tr '\n' ';' <"$CALLS"; }
row() { awk -F'\t' -v k="$1" '$1 == k { v = $2 "|" $3 } END { print v }' "$TMP/state"; }
# bak <имя>: копии <имя>.bak-* в sites-available, по строке
bak() { find "$SA" -maxdepth 1 -name "$1.bak-*" | sort; }

echo "[test] vhost панели и портала пересобраны: копия .bak-ГГГГММДД-ЧЧММСС, nginx -t, reload"
reset_nginx
run 'fu_run nginx fu_step_nginx'
[[ "$(row nginx)" == "ok|panel.example.com, portal.example.com" ]] && ok "итог ok" || bad "итог: $(row nginx); $(cat "$TMP/out")"
[[ "$(calls)" == "nginx -t;systemctl reload nginx;" ]] && ok "nginx -t, затем reload" || bad "вызовы: $(calls)"
for name in panel_example_com portal_example_com; do
  b="$(bak "$name")"
  if [[ "$(wc -l <<<"$b")" -eq 1 && "$b" =~ \.bak-[0-9]{8}-[0-9]{6}$ ]] && cmp -s "$b" "$TMP/$name.orig"; then
    ok "$name.bak-* — прежний файл"
  else
    bad "$name: копии: ${b:-нет}"
  fi
done
grep -qF "Копия: $SA/panel_example_com.bak-" "$TMP/out" && ok "путь копии напечатан" || bad "вывод: $(cat "$TMP/out")"
grep -qE 'server_name +panel\.example\.com;' "$SA/panel_example_com" \
  && grep -qF "ssl_certificate /etc/letsencrypt/live/panel.example.com/fullchain.pem;" "$SA/panel_example_com" \
  && grep -qF "ssl_certificate_key /etc/letsencrypt/live/panel.example.com/privkey.pem;" "$SA/panel_example_com" \
  && ok "vhost панели: домен и прежние сертификаты" || bad "vhost панели: $(cat "$SA/panel_example_com")"
grep -qF "/secret-path" "$SA/panel_example_com" && grep -qF "127.0.0.1:8000" "$SA/panel_example_com" \
  && ok "vhost панели: ACCESS_PATH и порт из .env" || bad "vhost панели: $(cat "$SA/panel_example_com")"
grep -qE 'server_name +portal\.example\.com;' "$SA/portal_example_com" \
  && grep -qF "ssl_certificate /etc/letsencrypt/live/portal.example.com/fullchain.pem;" "$SA/portal_example_com" \
  && ok "vhost портала" || bad "vhost портала: $(cat "$SA/portal_example_com")"
! grep -qE '^[^#]*__[A-Z_]+__' "$SA/panel_example_com" "$SA/portal_example_com" && ok "плейсхолдеры подставлены" \
  || bad "остались плейсхолдеры: $(grep -nE '^[^#]*__[A-Z_]+__' "$SA/panel_example_com" "$SA/portal_example_com")"
cmp -s "$INSTALL/backend/.env" "$TMP/env.orig" && [[ -L "$NG/sites-enabled/panel_example_com" ]] \
  && ok ".env и sites-enabled не тронуты" || bad ".env или sites-enabled изменены"
[[ -z "$(find "$NG/backups" -maxdepth 1 -name '.apaz-install.*')" ]] && ok "транзакция snippets зафиксирована" \
  || bad "остался каталог отката: $(find "$NG/backups" -maxdepth 1 -name '.apaz-install.*')"

echo "[test] nginx -t с ошибкой: старые файлы на месте, .bak остаются, reload нет, итог «ошибка», без стопа"
reset_nginx
touch "$TMP/nginx-fail"
run 'fu_run nginx fu_step_nginx; echo "stopped=$FU_STOPPED"'
[[ "$(row nginx)" == 'ошибка|конфиг не обновлён, старый восстановлен (nginx -t: [emerg] unknown directive "foo" in /etc/nginx/sites-enabled/panel_example_com:30)' ]] \
  && ok "итог «ошибка» со строкой nginx -t" || bad "итог: $(row nginx); $(cat "$TMP/out")"
[[ "$(calls)" == "nginx -t;nginx -t;" ]] && ok "nginx -t ещё раз после отката, без reload" || bad "вызовы: $(calls)"
cmp -s "$SA/panel_example_com" "$TMP/panel_example_com.orig" && cmp -s "$SA/portal_example_com" "$TMP/portal_example_com.orig" \
  && ok "прежние vhost возвращены" || bad "vhost не восстановлены: $(cat "$SA/panel_example_com")"
[[ -n "$(bak panel_example_com)" && -n "$(bak portal_example_com)" ]] && ok "копии .bak-* остались" || bad "копий нет"
[[ -z "$(ls -A "$NG/snippets")" && ! -e "$NG/conf.d/adminpanelaz-cloudflare-origin.conf" ]] \
  && ok "созданные snippets Cloudflare убраны" || bad "snippets: $(ls -A "$NG/snippets" "$NG/conf.d")"
grep -qx "stopped=false" "$TMP/out" && ok "обновление продолжается" || bad "вывод: $(cat "$TMP/out")"

echo "[test] публикация через nginx — по PUBLISH_MODE, без него — по BEHIND_NGINX; без DOMAIN — нет"
for case_ in "nginx_selfsigned||panel.example.com|yes" "nginx_custom||panel.example.com|yes" \
  "|true|panel.example.com|yes" "|false|panel.example.com|no" "nginx_le|true||no"; do
  IFS='|' read -r mode behind domain want <<<"$case_"
  printf 'DOMAIN=%s\nPUBLISH_MODE=%s\nBEHIND_NGINX=%s\n' "$domain" "$mode" "$behind" >"$INSTALL/backend/.env"
  run 'if fu_nginx_published; then echo yes; else echo no; fi'
  [[ "$(tail -n1 "$TMP/out")" == "$want" ]] && ok "PUBLISH_MODE=$mode BEHIND_NGINX=$behind DOMAIN=$domain — $want" \
    || bad "PUBLISH_MODE=$mode BEHIND_NGINX=$behind DOMAIN=$domain: $(cat "$TMP/out")"
done

echo "[test] публикация без nginx (uvicorn_le) — пропущен, файлы не тронуты"
reset_nginx "${NGINX_ENV/PUBLISH_MODE=nginx_le/PUBLISH_MODE=uvicorn_le}"
run 'fu_run nginx fu_step_nginx'
[[ "$(row nginx)" == "пропущен|публикация без nginx" && "$(calls)" == "" && -z "$(bak panel_example_com)" ]] \
  && cmp -s "$SA/panel_example_com" "$TMP/panel_example_com.orig" && ok "пропущен" \
  || bad "итог: $(row nginx), вызовы: $(calls)"

echo "[test] своего vhost нет (панель в подпути чужого сайта) — пропущен, nginx не менялся"
reset_nginx "${NGINX_ENV/PORTAL_DOMAIN=portal.example.com/PORTAL_DOMAIN=}"
printf 'server {\n    server_name panel.example.com;\n}\n' >"$SA/panel_example_com"
run 'fu_run nginx fu_step_nginx'
[[ "$(row nginx)" == "пропущен|нет своего vhost в $SA — nginx не менялся" && "$(calls)" == "" ]] \
  && ok "чужой vhost не тронут" || bad "итог: $(row nginx), вызовы: $(calls)"

echo "[test] сервер-узел без панели — пропущен"
reset_nginx
with_units adminpanelaz-node.service
run 'fu_run nginx fu_step_nginx'
[[ "$(row nginx)" == "пропущен|нет панели" && "$(calls)" == "" ]] && ok "нет панели" \
  || bad "итог: $(row nginx), вызовы: $(calls)"

echo "[test] полное обновление с ошибкой nginx -t: остальные шаги выполнены, перезапуск был, код 1"
reset_nginx
touch "$TMP/nginx-fail"
run 'full_update_main --yes'
[[ "$rc" -eq 1 ]] && ok "код 1" || bad "код $rc: $(cat "$TMP/out")"
[[ "$(calls)" == "backup --no-prune --keep-running;update;pip install -q -r $INSTALL/backend/requirements.txt;npm;refresh SYSTEMD_UNIT_DIR=$TMP/units;nginx -t;nginx -t;systemctl restart adminpanelaz;curl;" ]] \
  && ok "шаги после nginx выполнены" || bad "вызовы: $(calls)"
grep -qF '  nginx      ошибка    конфиг не обновлён, старый восстановлен (nginx -t: [emerg] unknown directive "foo"' "$TMP/out" \
  && grep -qxF "  Перезапуск ok        панель отвечает" "$TMP/out" && ok "итог" || bad "вывод: $(cat "$TMP/out")"
cmp -s "$SA/panel_example_com" "$TMP/panel_example_com.orig" && ok "старый vhost на месте" || bad "vhost изменён"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
