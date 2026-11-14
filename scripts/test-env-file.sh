#!/usr/bin/env bash
# scripts/env-file.sh: одна семантика чтения/записи .env для установщика, nginx, firewall и меню.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# shellcheck source=scripts/env-file.sh
source "$ROOT_DIR/scripts/env-file.sh"

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

ENV="$TMP_DIR/.env"

echo "[test] читается последнее присваивание (как у панели), кавычки и CR снимаются"
printf 'KEY=first\r\n# comment\r\nKEY="second value"\r\n' >"$ENV"
[[ "$(env_file_get "$ENV" KEY)" == "second value" ]] || fail "не последнее значение или остались кавычки/CR"
[[ "$(env_file_get "$ENV" MISSING)" == "" ]] || fail "отсутствующий ключ должен быть пустым"
echo "  OK"

echo "[test] запись обновляет все строки ключа и сохраняет остальные"
printf 'A=1\nB=2\nA=old\n' >"$ENV"
env_file_set "$ENV" A 'new value'
[[ "$(grep -c '^A=' "$ENV")" -ge 1 ]] || fail "ключ пропал"
[[ "$(grep -c '^A=new value$' "$ENV")" -eq "$(grep -c '^A=' "$ENV")" ]] || fail "одно из присваиваний не обновилось"
[[ "$(env_file_get "$ENV" A)" == "new value" ]] || fail "значение не записалось"
[[ "$(env_file_get "$ENV" B)" == "2" ]] || fail "потерян соседний ключ"
echo "  OK"

echo "[test] запись добавляет отсутствующий ключ и спецсимволы не ломают sed"
env_file_set "$ENV" C 'x&y|z\w'
[[ "$(env_file_get "$ENV" C)" == 'x&y|z\w' ]] || fail "значение со спецсимволами исказилось"
echo "  OK"

echo "[test] кавычки сохраняются только парные, одиночная кавычка — часть значения"
printf "Q1='single'\nQ2=\"a\n" >"$ENV"
[[ "$(env_file_get "$ENV" Q1)" == "single" ]] || fail "парные одинарные кавычки не снялись"
[[ "$(env_file_get "$ENV" Q2)" == '"a' ]] || fail "непарная кавычка должна остаться"
echo "  OK"

echo "[test] unset удаляет ключ и не падает без файла"
env_file_unset "$ENV" A
[[ -z "$(env_file_get "$ENV" A)" ]] || fail "ключ не удалён"
env_file_unset "$TMP_DIR/absent.env" A
echo "  OK"

echo "[test] перевод строки в значении отвергается"
if env_file_set "$TMP_DIR/bad.env" BAD $'a\nb' 2>/dev/null; then
  fail "многострочное значение записалось"
fi
echo "  OK"
