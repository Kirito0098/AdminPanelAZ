#!/usr/bin/env bash
# Проверка, что все режимы публикации install.sh имеют обработчик и согласованы с health-check.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pass=0
fail=0

assert_contains() {
  local haystack="$1" needle="$2" label="$3"
  if grep -qF -- "$needle" <<<"$haystack"; then
    pass=$((pass + 1))
    echo "  OK  $label"
  else
    fail=$((fail + 1))
    echo "  FAIL $label (missing: $needle)" >&2
  fi
}

install_body="$(sed -n '/setup_nginx_if_selected/,/^}/p' "$ROOT_DIR/install.sh")"
wizard_body="$(sed -n '/wizard_ask_https/,/^}/p' "$ROOT_DIR/scripts/install-wizard.sh")"
nginx_setup_body="$(cat "$ROOT_DIR/scripts/nginx-setup.sh")"

modes=(
  "le"
  "selfsigned"
  "nginx_custom"
  "uvicorn_le"
  "uvicorn_custom"
  "uvicorn_selfsigned"
  "none"
  "http_direct"
)

echo "[test] install.sh setup_nginx_if_selected — case для каждого режима"
for mode in "${modes[@]}"; do
  if [[ "$mode" == "none" ]]; then
  if grep -q 'if \[\[ "\$mode" == "none" \]\]' <<<"$install_body"; then
      pass=$((pass + 1))
      echo "  OK  none -> early return"
    else
      fail=$((fail + 1))
      echo "  FAIL none handler" >&2
    fi
    continue
  fi
  assert_contains "$install_body" "${mode})" "install case: $mode"
done

echo "[test] install-wizard — пункты меню 1-8"
for i in "${!modes[@]}"; do
  n=$((i + 1))
  mode="${modes[$i]}"
  assert_contains "$wizard_body" "${n}) WIZ_NGINX_MODE=\"${mode}\"" "wizard maps [$n] -> $mode"
done

echo "[test] nginx-setup.sh — CLI флаги для режимов"
flags=(
  "--nginx-le"
  "--nginx-selfsigned"
  "--nginx-custom"
  "--uvicorn-le"
  "--uvicorn-custom"
  "--uvicorn-selfsigned"
  "--http"
)
for flag in "${flags[@]}"; do
  assert_contains "$nginx_setup_body" "$flag" "nginx-setup flag $flag"
done

echo "[test] install.sh — helper-функции режимов"
helpers=(
  "is_uvicorn_https_mode"
  "is_nginx_https_mode"
  "is_direct_public_http_mode"
  "restart_services_after_nginx"
  "verify_controller_running"
  "bhc_wait_health"
)
install_all="$(cat "$ROOT_DIR/install.sh")"
for helper in "${helpers[@]}"; do
  assert_contains "$install_all" "$helper" "install defines/uses $helper"
done

echo "[test] backend-health-check — все режимы wizard"
# shellcheck source=scripts/backend-health-check.sh
source "$ROOT_DIR/scripts/backend-health-check.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BHC_ENV_FILE="$TMP/.env"
touch "$BHC_ENV_FILE"

for mode in "${modes[@]}"; do
  BHC_WIZ_NGINX_MODE="$mode"
  scheme="$(bhc_scheme_from_wizard 2>/dev/null || true)"
  case "$mode" in
    uvicorn_*)
      [[ "$scheme" == "https" ]] && { pass=$((pass + 1)); echo "  OK  bhc wizard $mode -> https"; } \
        || { fail=$((fail + 1)); echo "  FAIL bhc $mode" >&2; }
      ;;
    le|selfsigned|nginx_custom|none|http_direct)
      [[ "$scheme" == "http" ]] && { pass=$((pass + 1)); echo "  OK  bhc wizard $mode -> http"; } \
        || { fail=$((fail + 1)); echo "  FAIL bhc $mode" >&2; }
      ;;
  esac
done

echo
echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
