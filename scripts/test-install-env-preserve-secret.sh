#!/usr/bin/env bash
# Переустановка (--force / мастер) не должна менять SECRET_KEY: им зашифрованы ключи узлов и 2FA в БД.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

extract_functions() {
  local fn
  for fn in "$@"; do
    sed -n "/^${fn}() {/,/^}/p" "$ROOT_DIR/install.sh"
  done
}

run_reset() {
  ENV_FILE="$TMP_DIR/.env" ENV_EXAMPLE="$TMP_DIR/.env.example" bash -c '
    set -euo pipefail
    log() { :; }
    eval "$1"
    reset_env_from_example
  ' bash "$(extract_functions env_get env_escape_for_sed env_set is_placeholder_secret reset_env_from_example)"
}

printf 'SECRET_KEY=change-me-in-production-use-long-random-string\nAPP_ENV=development\n' >"$TMP_DIR/.env.example"

echo "[test] reset_env_from_example сохраняет существующий SECRET_KEY"
printf 'SECRET_KEY=existing-real-secret-0123456789abcdef\nAPP_ENV=production\nDOMAIN=old.example\n' >"$TMP_DIR/.env"
run_reset
grep -qx 'SECRET_KEY=existing-real-secret-0123456789abcdef' "$TMP_DIR/.env"
grep -qx 'APP_ENV=development' "$TMP_DIR/.env"
if grep -q '^DOMAIN=' "$TMP_DIR/.env"; then
  echo "  FAIL остальные значения должны сбрасываться к .env.example" >&2
  exit 1
fi
echo "  OK"

echo "[test] reset_env_from_example не переносит плейсхолдер SECRET_KEY"
printf 'SECRET_KEY=change-me\n' >"$TMP_DIR/.env"
run_reset
grep -qx 'SECRET_KEY=change-me-in-production-use-long-random-string' "$TMP_DIR/.env"
echo "  OK"

echo "[test] setup_env ограничивает права backend/.env до 600"
setup_env_body="$(sed -n '/^setup_env() {/,/^}/p' "$ROOT_DIR/install.sh")"
if ! grep -qF 'chmod 600 "$ENV_FILE"' <<<"$setup_env_body"; then
  echo "  FAIL setup_env не выполняет chmod 600 \"\$ENV_FILE\"" >&2
  exit 1
fi
echo "  OK"
