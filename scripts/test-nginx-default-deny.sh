#!/usr/bin/env bash
# Без сервера по умолчанию nginx отдаёт запросы по голому IP и чужим именам vhost'у панели.
# Проверки передаются в check строкой и раскрываются через eval.
# shellcheck disable=SC2016,SC2034
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ENV_FILE="$TMP/.env"
: >"$ENV_FILE"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

export NGINX_SITES_AVAILABLE_DIR="$TMP/sites-available"
export NGINX_SITES_ENABLED_DIR="$TMP/sites-enabled"
export NGINX_CONF_D_DIR="$TMP/conf.d"
export NGINX_DEFAULT_DENY_CERT="$TMP/ssl/deny.crt"
export NGINX_DEFAULT_DENY_KEY="$TMP/ssl/deny.key"
mkdir -p "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR" "$NGINX_CONF_D_DIR"
AVAIL="$NGINX_SITES_AVAILABLE_DIR"
ENABLED="$NGINX_SITES_ENABLED_DIR"
DENY="$AVAIL/00-adminpanelaz-default-deny"
DENY_LINK="$ENABLED/00-adminpanelaz-default-deny"

REAL_NGINX="$(command -v nginx || true)"
FAKE_NGINX_VERSION="1.24.0"
FAKE_T_FAIL_WITH_DENY=0
FAKE_T_FILES=""
# Функции перекрывают настоящие nginx/systemctl: тест не трогает nginx сервера.
nginx() {
  local f
  case "${1:-}" in
    -v) echo "nginx version: nginx/${FAKE_NGINX_VERSION}" >&2 ;;
    -T)
      for f in $FAKE_T_FILES; do
        printf '# configuration file %s:\n' "$f"
        cat "$f"
      done
      ;;
    -t)
      if [[ "$FAKE_T_FAIL_WITH_DENY" == 1 && -e "$DENY_LINK" ]]; then
        echo "nginx: [emerg] duplicate default server" >&2
        return 1
      fi
      return 0
      ;;
    *) return 0 ;;
  esac
}
systemctl() {
  local deny=off
  [[ -e "$DENY_LINK" ]] && deny=on
  echo "systemctl $* deny=$deny" >>"$TMP/systemctl.log"
}

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }
check() { if eval "$1"; then ok "$2"; else bad "$2"; fi; }

PANEL_CONF='server {
    listen 8080;
    server_name panel.example.com;
    return 301 https://$host$request_uri;
}
server {
    listen 8443 ssl http2;
    server_name panel.example.com;
}'

reset() {
  rm -rf "${AVAIL:?}"/* "${ENABLED:?}"/* "${NGINX_CONF_D_DIR:?}"/* "$TMP/ssl"
  FAKE_NGINX_VERSION="1.24.0"
  FAKE_T_FAIL_WITH_DENY=0
  FAKE_T_FILES=""
}

# site <имя> <содержимое>: включённый сайт в sites-enabled
site() {
  printf '%s\n' "$2" >"$AVAIL/$1"
  ln -sf "$AVAIL/$1" "$ENABLED/$1"
}

install_panel() {
  ( nginx_install_site "${1:-$PANEL_CONF}" "${2:-panel.example.com}" ) >/dev/null 2>&1
}

echo "[test] установка vhost панели ставит сервер по умолчанию на её порты"
reset
( nginx_install_site "$PANEL_CONF" panel.example.com ) >/dev/null 2>&1
check '[[ -L "$DENY_LINK" && -f "$DENY" ]]' "default-deny установлен и включён"
check 'grep -Eq "^[[:space:]]*listen 8080 default_server;" "$DENY"' "HTTP-порт панели: default_server"
check 'grep -Eq "^[[:space:]]*listen 8443 ssl default_server;" "$DENY"' "HTTPS-порт панели: default_server"
check 'grep -q "return 444;" "$DENY"' "HTTP: соединение закрывается без ответа"
check 'grep -q "ssl_reject_handshake on;" "$DENY"' "HTTPS на nginx ≥ 1.19.4: рукопожатие отклоняется"
check '! grep -q "ssl_certificate" "$DENY"' "сертификат не нужен при ssl_reject_handshake"

echo "[test] повторная установка не считает свой default-deny чужим"
( nginx_install_site "$PANEL_CONF" panel.example.com ) >/dev/null 2>&1
check 'grep -q "listen 8080 default_server;" "$DENY" && grep -q "listen 8443 ssl default_server;" "$DENY"' "оба порта на месте после повтора"

echo "[test] nginx 1.18: самоподписанный сертификат вместо ssl_reject_handshake"
reset
FAKE_NGINX_VERSION="1.18.0"
( nginx_install_site "$PANEL_CONF" panel.example.com ) >/dev/null 2>&1
check '! grep -q "ssl_reject_handshake" "$DENY"' "нет ssl_reject_handshake"
check 'grep -q "ssl_certificate $NGINX_DEFAULT_DENY_CERT;" "$DENY"' "указан свой сертификат"
check '[[ -s "$NGINX_DEFAULT_DENY_CERT" && -s "$NGINX_DEFAULT_DENY_KEY" ]]' "сертификат создан"
check '[[ "$(stat -c %a "$NGINX_DEFAULT_DENY_KEY")" == 600 ]]' "ключ 600"
check '[[ "$(grep -c "return 444;" "$DENY")" == 2 ]]' "оба сервера отвечают 444"

echo "[test] чужой default_server на порту не трогается"
reset
printf 'server {\n    listen 8080 default_server;\n    listen [::]:8080 default_server;\n    return 404;\n}\n' >"$AVAIL/other"
ln -s "$AVAIL/other" "$ENABLED/other"
( nginx_install_site "$PANEL_CONF" panel.example.com ) >/dev/null 2>&1
check '! grep -q "listen 8080" "$DENY"' "HTTP-порт с чужим default_server пропущен"
check 'grep -q "listen 8443 ssl default_server;" "$DENY"' "HTTPS-порт закрыт"
printf 'server {\n    listen 0.0.0.0:8443 ssl default_server;\n}\n' >"$NGINX_CONF_D_DIR/other.conf"
( nginx_install_site "$PANEL_CONF" panel.example.com ) >/dev/null 2>&1
check '[[ ! -e "$DENY" && ! -L "$DENY_LINK" ]]' "оба порта заняты чужими default_server — файла нет"
rm -f "$NGINX_CONF_D_DIR/other.conf"

echo "[test] порт 80 не путается с 8080, выключенный сайт не считается"
reset
printf 'server {\n    listen 80 default_server;\n}\n' >"$AVAIL/disabled-default"
printf 'server {\n    listen 18080 default_server;\n    # listen 8080 default_server;\n}\n' >"$AVAIL/near"
ln -s "$AVAIL/near" "$ENABLED/near"
( nginx_install_site "$PANEL_CONF" panel.example.com ) >/dev/null 2>&1
check 'grep -q "listen 8080 default_server;" "$DENY"' "18080 и закомментированный listen не мешают"

echo "[test] панель по IP: HTTPS-порт не закрывается (клиент по IP не шлёт SNI и попал бы в отказ)"
reset
install_panel "${PANEL_CONF//panel.example.com/203.0.113.10}" 203.0.113.10
check 'grep -q "listen 8080 default_server;" "$DENY"' "HTTP-порт закрыт: Host с IP совпадает с server_name панели"
check '! grep -q "8443" "$DENY"' "HTTPS-порт панели по IP не закрыт"
reset
install_panel "${PANEL_CONF//panel.example.com/2001:db8::10}" "2001:db8::10"
check '! grep -q "8443" "$DENY"' "то же для IPv6-адреса в server_name"

echo "[test] чужой сайт объявлен раньше панели — он и отвечает по IP, порт не трогаем"
reset
site aaa 'server {
    listen 8080;
    server_name a.example;
}'
install_panel
check '! grep -q "listen 8080" "$DENY"' "порт, где первым идёт чужой сайт, пропущен"
check 'grep -q "listen 8443 ssl default_server;" "$DENY"' "порт, где панель первая, закрыт"

echo "[test] чужой сайт после панели не мешает"
reset
site zzz 'server { listen 8080; listen 8443 ssl; server_name z.example; }'
install_panel
check 'grep -q "listen 8080 default_server;" "$DENY" && grep -q "listen 8443 ssl default_server;" "$DENY"' "оба порта закрыты"

echo "[test] чужой HTTPS-сайт по IP после панели: его HTTPS-порт не закрывается"
reset
site zzz 'server { listen 8080; listen 8443 ssl; server_name z.example 203.0.113.20; }'
install_panel
check '! grep -q "8443" "$DENY"' "HTTPS-порт чужого сайта по IP не закрыт (без SNI он попал бы в отказ)"
check 'grep -q "listen 8080 default_server;" "$DENY"' "HTTP-порт закрыт: Host с IP совпадает с server_name чужого сайта"
reset
site zzz 'server { listen 9443 ssl; server_name 2001:db8::20; }'
install_panel
check 'grep -q "listen 8443 ssl default_server;" "$DENY"' "сайт по IP на другом порту не мешает закрыть HTTPS-порт панели"

echo "[test] чужой default_server после панели тоже отвечает по IP — порт не трогаем"
reset
site zzz '# old: server { listen 8443 ssl default_server; }
server { listen 8080 default_server; server_name z.example; }'
install_panel
check '! grep -q "listen 8080" "$DENY"' "порт с чужим default_server пропущен"
check 'grep -q "listen 8443 ssl default_server;" "$DENY"' "закомментированный listen со скобкой не считается"

echo "[test] conf.d загружается раньше sites-enabled"
reset
printf 'server { listen 8443 ssl; server_name z.example; }\n' >"$NGINX_CONF_D_DIR/zzz.conf"
install_panel
check '! grep -q "8443" "$DENY"' "чужой сайт из conf.d первый на 8443"
check 'grep -q "listen 8080 default_server;" "$DENY"' "8080 закрыт"

echo "[test] порядок из nginx -T важнее имён файлов"
reset
site zzz 'server { listen 8080; server_name z.example; }'
FAKE_T_FILES="$ENABLED/zzz $ENABLED/panel_example_com"
install_panel
check '! grep -q "listen 8080" "$DENY"' "по nginx -T чужой сайт первый на 8080"
check 'grep -q "listen 8443 ssl default_server;" "$DENY"' "8443 закрыт"

echo "[test] портал и панель: сервер по умолчанию закрывает порты обоих"
reset
site portal_example_com '# AdminPanelAZ — Client portal reverse proxy (шаблон)
server {
    listen 9080;
    listen 8080;
    server_name portal.example.com;
}
server {
    listen 9443 ssl http2;
    server_name portal.example.com;
}'
install_panel
for p in "8080 " "9080 " "8443 ssl " "9443 ssl "; do
  check "grep -q 'listen ${p}default_server;' \"\$DENY\"" "listen ${p}default_server"
done
check '[[ "$(grep -c "listen 8080 default_server;" "$DENY")" == 1 ]]' "общий порт 8080 объявлен один раз"

echo "[test] адрес и IPv6 из listen панели повторяются в сервере по умолчанию"
reset
install_panel 'server {
    listen 8080;
    listen [::]:8080;
    server_name panel.example.com;
}
server {
    listen 127.0.0.1:8443 ssl;
    server_name panel.example.com;
}'
check 'grep -q "listen \[::\]:8080 default_server;" "$DENY"' "IPv6-порт закрыт"
check 'grep -q "listen 127.0.0.1:8443 ssl default_server;" "$DENY"' "адрес из listen сохранён"

echo "[test] не удалось записать файл default-deny — установка панели не падает"
reset
ln -s "$TMP/nope/deny" "$DENY"
rc=0
install_panel || rc=$?
check '[[ "$rc" == 0 ]]' "установка панели прошла"
check '[[ ! -L "$DENY_LINK" ]]' "default-deny не включён"

echo "[test] default-deny не прошёл nginx -t — откат, панель остаётся"
reset
FAKE_T_FAIL_WITH_DENY=1
( nginx_install_site "$PANEL_CONF" panel.example.com ) >/dev/null 2>&1
rc=$?
check '[[ "$rc" == 0 ]]' "установка панели не падает"
check '[[ ! -e "$DENY" && ! -L "$DENY_LINK" ]]' "default-deny убран"
check '[[ -L "$ENABLED/panel_example_com" ]]' "vhost панели включён"

echo "[test] переход на прямую публикацию убирает default-deny и не считает его чужим сайтом"
reset
( nginx_install_site "$PANEL_CONF" panel.example.com ) >/dev/null 2>&1
: >"$TMP/systemctl.log"
( nginx_disable_for_direct_publish panel.example.com ) >/dev/null 2>&1
check '[[ ! -e "$DENY" && ! -L "$DENY_LINK" ]]' "default-deny удалён"
check 'grep -q "systemctl stop nginx" "$TMP/systemctl.log"' "без других сайтов nginx останавливается"

echo "[test] прямая публикация при чужих сайтах: default-deny удалён, nginx перезагружен"
reset
( nginx_install_site "$PANEL_CONF" panel.example.com ) >/dev/null 2>&1
printf 'server { listen 80; server_name other.example; }\n' >"$AVAIL/other"
ln -s "$AVAIL/other" "$ENABLED/other"
: >"$TMP/systemctl.log"
( nginx_disable_for_direct_publish panel.example.com ) >/dev/null 2>&1
check '[[ ! -e "$DENY_LINK" ]]' "default-deny удалён"
check '! grep -q "systemctl stop nginx" "$TMP/systemctl.log"' "nginx не остановлен"
check '[[ "$(grep "systemctl reload nginx" "$TMP/systemctl.log" | tail -1)" == *deny=off ]]' "последняя перезагрузка nginx — уже без default-deny"

echo "[test] живой nginx: голый IP отклоняется, домен панели работает, панель по IP открывается (пропуск без nginx)"
if [[ -n "$REAL_NGINX" ]] && command -v curl >/dev/null 2>&1 && command -v openssl >/dev/null 2>&1; then
  NGX="$TMP/ngx"
  mkdir -p "$NGX/logs" "$NGX/sites-available" "$NGX/sites-enabled" "$NGX/conf.d"
  export NGINX_SITES_AVAILABLE_DIR="$NGX/sites-available"
  export NGINX_SITES_ENABLED_DIR="$NGX/sites-enabled"
  export NGINX_CONF_D_DIR="$NGX/conf.d"
  DENY_LINK="$NGX/sites-enabled/00-adminpanelaz-default-deny"
  # Настоящий nginx со своим префиксом: default-deny ставится по его nginx -T и nginx -t.
  nginx() { "$REAL_NGINX" -p "$NGX" -c "$NGX/nginx.conf" "$@"; }
  openssl req -x509 -nodes -days 1 -newkey rsa:2048 -subj "/CN=panel.test" \
    -keyout "$NGX/panel.key" -out "$NGX/panel.crt" >/dev/null 2>&1
  HTTP_L="127.0.0.1:18490"
  HTTPS_L="127.0.0.1:18491"
  {
    printf 'pid %s/nginx.pid;\nerror_log %s/logs/error.log;\nevents {}\nhttp {\n' "$NGX" "$NGX"
    printf '  access_log off;\n  client_body_temp_path %s; proxy_temp_path %s; fastcgi_temp_path %s; uwsgi_temp_path %s; scgi_temp_path %s;\n' "$NGX" "$NGX" "$NGX" "$NGX" "$NGX"
    printf '  include %s/conf.d/*.conf;\n  include %s/sites-enabled/*;\n}\n' "$NGX" "$NGX"
  } >"$NGX/nginx.conf"

  # live_panel <server_name>: vhost панели, default-deny по живому nginx, запуск nginx
  live_panel() {
    rm -f "$NGX"/sites-enabled/* "$NGX"/sites-available/*
    NGINX_CONF_FILE="$NGX/sites-available/panel"
    {
      printf '# AdminPanelAZ — Nginx reverse proxy (шаблон)\n'
      printf 'server { listen %s; server_name %s; location / { return 200 "panel"; } }\n' "$HTTP_L" "$1"
      printf 'server { listen %s ssl; server_name %s; ssl_certificate %s/panel.crt; ssl_certificate_key %s/panel.key; location / { return 200 "panel"; } }\n' "$HTTPS_L" "$1" "$NGX" "$NGX"
    } >"$NGINX_CONF_FILE"
    ln -s "$NGINX_CONF_FILE" "$NGX/sites-enabled/panel"
    nginx_install_default_deny >/dev/null 2>&1
    if nginx -t -q 2>"$NGX/t.err" && nginx 2>>"$NGX/t.err"; then
      sleep 0.3
      return 0
    fi
    cat "$NGX/t.err" >&2
    return 1
  }
  live_stop() {
    nginx -s stop 2>/dev/null || true
    sleep 0.3
  }

  if live_panel panel.test; then
    check '[[ -L "$DENY_LINK" ]]' "default-deny поставлен по живому nginx -T"
    body="$(curl -s -H 'Host: panel.test' "http://$HTTP_L/" || true)"
    check '[[ "$body" == panel ]]' "HTTP: домен панели отвечает"
    set +e
    curl -s -o /dev/null -H 'Host: 203.0.113.7' "http://$HTTP_L/"
    rc_ip=$?
    curl -sk -o /dev/null "https://$HTTPS_L/"
    rc_tls_ip=$?
    set -e
    check '[[ "$rc_ip" == 52 ]]' "HTTP по IP: соединение закрыто без ответа (curl 52, было $rc_ip)"
    check '[[ "$rc_tls_ip" != 0 ]]' "HTTPS по IP: ответа нет (curl $rc_tls_ip)"
    body="$(curl -sk --resolve "panel.test:18491:127.0.0.1" "https://panel.test:18491/" || true)"
    check '[[ "$body" == panel ]]' "HTTPS: домен панели отвечает"
    live_stop
  else
    bad "живой nginx не принял конфиг (домен)"
  fi

  if live_panel 127.0.0.1; then
    body="$(curl -sk "https://$HTTPS_L/" || true)"
    check '[[ "$body" == panel ]]' "панель по IP: HTTPS открывается"
    body="$(curl -s "http://$HTTP_L/" || true)"
    check '[[ "$body" == panel ]]' "панель по IP: HTTP открывается"
    set +e
    curl -s -o /dev/null -H 'Host: other.example' "http://$HTTP_L/"
    rc_other=$?
    set -e
    check '[[ "$rc_other" == 52 ]]' "панель по IP: чужое имя по HTTP отклоняется (curl $rc_other)"
    live_stop
  else
    bad "живой nginx не принял конфиг (IP)"
  fi
else
  echo "  SKIP nginx/curl/openssl не установлены"
fi

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
