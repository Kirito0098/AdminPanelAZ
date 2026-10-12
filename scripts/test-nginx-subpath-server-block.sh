#!/usr/bin/env bash
# Подпуть на домене с чужим сайтом: include snippet панели встаёт в блок server с нужным server_name и
# HTTPS-listen, а не после первого «listen 443» в файле (там может быть другой домен или комментарий).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# Не рабочий backend/.env: библиотека пишет в ENV_FILE.
ENV_FILE="$TMP/.env"
: >"$ENV_FILE"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

export NGINX_SNIPPETS_DIR="$TMP/nginx/snippets"
export NGINX_BACKUPS_DIR="$TMP/nginx/backups"
export NGINX_SITES_AVAILABLE_DIR="$TMP/nginx/sites-available"
export NGINX_SITES_ENABLED_DIR="$TMP/nginx/sites-enabled"
DOMAIN="panel.example.com"
INCLUDE="snippets/adminpanelaz-panel_example_com-panel.conf"
VHOST="$NGINX_SITES_AVAILABLE_DIR/site.example.com"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

for f in nginx_sites_available_dir nginx_sites_enabled_dir nginx_backups_dir nginx_snippets_dir; do
  if [[ "$("$f")" != "$TMP"/* ]]; then
    echo "  FAIL $f не во временном каталоге: $("$f") — тест не запускается" >&2
    exit 1
  fi
done

reset_tree() {
  rm -rf "$TMP/nginx"
  mkdir -p "$NGINX_SNIPPETS_DIR" "$NGINX_BACKUPS_DIR" "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR"
}

run_quiet() {
  set +e
  ( "$@" ) >"$TMP/out" 2>&1
  rc=$?
  set -e
}

echo "[test] include — в server нужного домена после первого HTTPS-listen"
reset_tree
cat >"$VHOST" <<'EOF'
# listen 443 ssl; server_name panel.example.com;
server {
    listen 443 ssl;
    server_name other.example.com;
    root /srv/other;
}
server {
    listen 80;
    server_name panel.example.com;
    return 301 https://$host$request_uri;
}
server {
    server_name www.panel.example.com panel.example.com;
    listen [::]:443 ssl;
    listen 443 ssl;
    location / {
        root /srv/panel;
    }
}
EOF
cat >"$TMP/expected" <<'EOF'
# listen 443 ssl; server_name panel.example.com;
server {
    listen 443 ssl;
    server_name other.example.com;
    root /srv/other;
}
server {
    listen 80;
    server_name panel.example.com;
    return 301 https://$host$request_uri;
}
server {
    server_name www.panel.example.com panel.example.com;
    listen [::]:443 ssl;

    include snippets/adminpanelaz-panel_example_com-panel.conf;
    listen 443 ssl;
    location / {
        root /srv/panel;
    }
}
EOF
run_quiet _nginx_integrate_subpath_into_vhost_file "$VHOST" "$INCLUDE" "$DOMAIN"
[[ "$rc" -eq 0 ]] && ok "include добавлен" || bad "код $rc: $(tail -3 "$TMP/out")"
if diff -u "$TMP/expected" "$VHOST" >"$TMP/diff"; then
  ok "include в server домена с HTTPS"
else
  bad "vhost: $(cat "$TMP/diff")"
fi

echo "[test] повторный вызов — include не дублируется"
run_quiet _nginx_integrate_subpath_into_vhost_file "$VHOST" "$INCLUDE" "$DOMAIN"
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(tail -3 "$TMP/out")"
diff -q "$TMP/expected" "$VHOST" >/dev/null && ok "файл не изменился" || bad "файл изменился: $(diff "$TMP/expected" "$VHOST" | tr '\n' ' ')"

echo "[test] у домена только HTTP-блок — include не добавляется, файл не меняется"
reset_tree
cat >"$VHOST" <<'EOF'
server {
    listen 443 ssl;
    server_name other.example.com;
}
server {
    listen 80;
    server_name panel.example.com;
}
EOF
cp "$VHOST" "$TMP/before"
run_quiet _nginx_integrate_subpath_into_vhost_file "$VHOST" "$INCLUDE" "$DOMAIN"
[[ "$rc" -ne 0 ]] && ok "отказ" || bad "include добавлен в чужой домен"
cmp -s "$TMP/before" "$VHOST" && ok "файл не изменён" || bad "файл изменён: $(diff "$TMP/before" "$VHOST" | tr '\n' ' ')"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
