#!/usr/bin/env bash
# Проверка режимов публикации: install.sh handlers, default wizard http_direct, nginx-setup, health-check.
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

assert_not_contains() {
  local haystack="$1" needle="$2" label="$3"
  if grep -qF -- "$needle" <<<"$haystack"; then
    fail=$((fail + 1))
    echo "  FAIL $label (unexpected: $needle)" >&2
  else
    pass=$((pass + 1))
    echo "  OK  $label"
  fi
}

install_body="$(sed -n '/setup_nginx_if_selected/,/^}/p' "$ROOT_DIR/install.sh")"
wizard_all="$(cat "$ROOT_DIR/scripts/install-wizard.sh")"
publish_fn="$(sed -n '/wizard_apply_default_publish_http_direct/,/^}/p' "$ROOT_DIR/scripts/install-wizard.sh")"
run_wizard_fn="$(sed -n '/^run_install_wizard()/,/^}/p' "$ROOT_DIR/scripts/install-wizard.sh")"
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

echo "[test] install-wizard — дефолт публикации http_direct (без интерактивного HTTPS)"
assert_contains "$publish_fn" 'WIZ_NGINX_MODE="http_direct"' "default sets http_direct"
assert_contains "$publish_fn" 'WIZ_BACKEND_HOST="0.0.0.0"' "default sets BACKEND_HOST 0.0.0.0"
assert_contains "$run_wizard_fn" "wizard_apply_default_publish_http_direct" "run_install_wizard calls default publish"
assert_not_contains "$run_wizard_fn" "wizard_ask_https" "run_install_wizard does not call wizard_ask_https"
assert_contains "$wizard_all" 'WIZ_NGINX_MODE="${WIZ_NGINX_MODE:-http_direct}"' "WIZ_NGINX_MODE default http_direct"

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

# Needles built at runtime so this file stays free of the retired installer name.
_easy_script="$(printf 'install-%s' 'easy')"
_easy_wizard="$(printf 'install-%s-wizard' 'easy')"
_easy_flag="$(printf -- '--%s)' 'easy')"
_easy_blob="$install_all$wizard_all"
if grep -qF -- "$_easy_script" <<<"$_easy_blob" \
  || grep -qF -- "$_easy_wizard" <<<"$_easy_blob" \
  || grep -qF -- "$_easy_flag" <<<"$_easy_blob" \
  || grep -qF -- 'EASY_MODE' <<<"$_easy_blob"; then
  fail=$((fail + 1))
  echo "  FAIL leftover easy-installer refs in install/wizard" >&2
else
  pass=$((pass + 1))
  echo "  OK  no easy-installer refs in install/wizard"
fi

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
