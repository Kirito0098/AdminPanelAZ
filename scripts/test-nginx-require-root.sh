#!/usr/bin/env bash
# nginx-setup.sh, nginx-repair.sh и nginx-default-deny.sh проверяют root через nginx_require_root
# из nginx-common.sh: не root — одна строка в stderr и код 1 до любых изменений. В nginx-common.sh
# нет функции require_root: install.sh подключает библиотеку после своей require_root (с перезапуском
# через sudo), и одноимённая функция библиотеки заменила бы её.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export ENV_FILE="$TMP/.env"
: >"$ENV_FILE"
export CALLS_LOG="$TMP/calls.log"
: >"$CALLS_LOG"
mkdir -p "$TMP/bin"
cat >"$TMP/bin/id" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == -u ]] && { echo 1000; exit 0; }
exec /usr/bin/id "$@"
EOF
for cmd in nginx systemctl apt-get certbot snap openssl; do
  printf '#!/usr/bin/env bash\necho "%s $*" >>"$CALLS_LOG"\nexit 1\n' "$cmd" >"$TMP/bin/$cmd"
done
chmod +x "$TMP/bin/"*

pass=0
fail=0
ok() { echo "  OK $*"; pass=$((pass + 1)); }
bad() { echo "  FAIL $*" >&2; fail=$((fail + 1)); }

echo "[test] nginx-common.sh: есть nginx_require_root, нет require_root"
if grep -q '^nginx_require_root() {' "$ROOT_DIR/scripts/nginx-common.sh"; then
  ok "nginx_require_root определена"
else
  bad "nginx_require_root не определена"
fi
if grep -Eq '^require_root\(\)' "$ROOT_DIR/scripts/nginx-common.sh"; then
  bad "require_root в nginx-common.sh заменит функцию install.sh"
else
  ok "require_root не определена"
fi

check_not_root() {
  local name="$1" script rc=0 stderr
  shift
  script="$ROOT_DIR/scripts/$name"
  echo "[test] $name $*: запуск не от root"
  if grep -Eq '^require_root\(\)' "$script"; then
    bad "$name: своя копия require_root"
  else
    ok "$name: своей require_root нет"
  fi
  : >"$CALLS_LOG"
  PATH="$TMP/bin:$PATH" bash "$script" "$@" >"$TMP/stdout" 2>"$TMP/stderr" || rc=$?
  if [[ "$rc" == 1 ]]; then ok "$name: код 1"; else bad "$name: код $rc"; fi
  stderr="$(cat "$TMP/stderr")"
  if [[ "$stderr" == "[nginx-setup] ОШИБКА: Запустите от root: sudo ${script}" ]]; then
    ok "$name: сообщение"
  else
    bad "$name: stderr '${stderr}'"
  fi
  if [[ ! -s "$TMP/stdout" ]]; then ok "$name: stdout пуст"; else bad "$name: stdout '$(cat "$TMP/stdout")'"; fi
  if [[ ! -s "$CALLS_LOG" ]]; then ok "$name: nginx/systemctl не вызывались"; else bad "$name: вызовы $(cat "$CALLS_LOG")"; fi
}

check_not_root nginx-setup.sh --non-interactive --http
check_not_root nginx-repair.sh --non-interactive
check_not_root nginx-default-deny.sh --check

echo
echo "Итого: OK=${pass} FAIL=${fail}"
[[ "$fail" -eq 0 ]]
