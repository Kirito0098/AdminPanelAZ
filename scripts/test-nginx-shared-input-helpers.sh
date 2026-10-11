#!/usr/bin/env bash
# nginx_is_non_interactive и nginx_validate_port из nginx-common.sh — общие для nginx-setup.sh и nginx-repair.sh:
# своих копий is_non_interactive / validate_port в скриптах нет, вызовы идут через имена с префиксом nginx_.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ENV_FILE="$TMP/.env"
: >"$ENV_FILE"

# shellcheck source=scripts/nginx-common.sh
source "$ROOT_DIR/scripts/nginx-common.sh"
nginx_common_init

pass=0
fail=0
ok() { echo "  OK $*"; pass=$((pass + 1)); }
bad() { echo "  FAIL $*" >&2; fail=$((fail + 1)); }

echo "[test] nginx-common.sh: функции определены"
for fn in nginx_is_non_interactive nginx_validate_port; do
  if declare -F "$fn" >/dev/null; then ok "$fn"; else bad "$fn не определена"; fi
done

echo "[test] nginx_validate_port: 1..65535 — код 0, иначе ошибка с меткой и код 1"
for port in 1 80 8000 65535; do
  if (nginx_validate_port "$port" "PORT") 2>"$TMP/err" && [[ ! -s "$TMP/err" ]]; then
    ok "порт $port принят"
  else
    bad "порт $port отклонён: $(cat "$TMP/err")"
  fi
done
for port in 0 65536 abc "" "-1" "80 81"; do
  rc=0
  (nginx_validate_port "$port" "HTTPS_PUBLIC_PORT") 2>"$TMP/err" || rc=$?
  if [[ "$rc" == 1 && "$(cat "$TMP/err")" == "[nginx-setup] ОШИБКА: HTTPS_PUBLIC_PORT: некорректный порт (1-65535)" ]]; then
    ok "порт '$port' отклонён"
  else
    bad "порт '$port': код $rc, stderr '$(cat "$TMP/err")'"
  fi
done

echo "[test] nginx_is_non_interactive: NON_INTERACTIVE=true|1 или stdin не терминал"
for value in true 1; do
  if NON_INTERACTIVE="$value" nginx_is_non_interactive </dev/null; then ok "NON_INTERACTIVE=$value"; else bad "NON_INTERACTIVE=$value"; fi
done
if NON_INTERACTIVE=false nginx_is_non_interactive </dev/null; then
  ok "NON_INTERACTIVE=false, stdin не терминал"
else
  bad "NON_INTERACTIVE=false, stdin не терминал — считается интерактивным"
fi

echo "[test] nginx-setup.sh и nginx-repair.sh: без своих копий и без старых имён"
for name in nginx-setup.sh nginx-repair.sh; do
  script="$ROOT_DIR/scripts/$name"
  if grep -Eq '^(is_non_interactive|validate_port)\(\)' "$script"; then
    bad "$name: своя копия is_non_interactive / validate_port"
  else
    ok "$name: своих копий нет"
  fi
  if grep -Eq '(^|[^_[:alnum:]])(is_non_interactive|validate_port)([^_[:alnum:]]|$)' "$script"; then
    bad "$name: вызов без префикса nginx_: $(grep -En '(^|[^_[:alnum:]])(is_non_interactive|validate_port)([^_[:alnum:]]|$)' "$script" | head -1)"
  else
    ok "$name: вызовы через nginx_"
  fi
done

echo
echo "Итого: OK=${pass} FAIL=${fail}"
[[ "$fail" -eq 0 ]]
