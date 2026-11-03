#!/usr/bin/env bash
# Шаг «Сервисы»: модуль Telegram и авто-бэкап. Telegram — только вкл/выкл (без токена),
# авто-бэкап — 7 дней / свой срок 1–90 / выключить. Решение мастера обязано попасть в БД
# и в backend/.env после сценария (иначе пресет перетирает FEATURE_TELEGRAM_ENABLED).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

extract() {
  local file="$1" fn
  shift
  for fn in "$@"; do
    sed -n "/^${fn}() {/,/^}/p" "$file"
  done
}

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

WIZ_FNS="$(extract "$ROOT_DIR/scripts/install-wizard.sh" \
  wiz_prompt wiz_prompt_yesno wiz_prompt_choice wizard_ask_extras)"

# run_extras <accept_defaults> <stdin>: печатает «telegram backup days»
run_extras() {
  local accept="$1" input="${2:-}"
  ACCEPT="$accept" bash -c '
    set -euo pipefail
    wiz_step() { :; }
    WIZ_INSTALL_TYPE=controller
    WIZ_ACCEPT_DEFAULTS="$ACCEPT"
    WIZ_TELEGRAM_ENABLED=true
    WIZ_AUTO_BACKUP_ENABLED=true
    WIZ_AUTO_BACKUP_DAYS=7
    eval "$1"
    wizard_ask_extras
    echo "$WIZ_TELEGRAM_ENABLED $WIZ_AUTO_BACKUP_ENABLED $WIZ_AUTO_BACKUP_DAYS"
  ' bash "$WIZ_FNS" <<<"$input" | tail -1
}

echo "[test] -y: Telegram включён, авто-бэкап каждые 7 дней"
[[ "$(run_extras true)" == "true true 7" ]] || fail "получено: $(run_extras true)"
echo "  OK"

echo "[test] Telegram off + авто-бэкап выключен"
[[ "$(run_extras false $'n\n3')" == "false false 7" ]] || fail "получено: $(run_extras false $'n\n3')"
echo "  OK"

echo "[test] свой срок: 30 дней"
[[ "$(run_extras false $'y\n2\n30')" == "true true 30" ]] || fail "получено: $(run_extras false $'y\n2\n30')"
echo "  OK"

echo "[test] свой срок: мусор и 0 отклоняются, принимается 14"
[[ "$(run_extras false $'y\n2\nabc\n0\n14')" == "true true 14" ]] \
  || fail "получено: $(run_extras false $'y\n2\nabc\n0\n14')"
echo "  OK"

echo "[test] -y не задаёт вопросов (stdin пуст)"
out="$(run_extras true "" </dev/null)" || fail "run_extras -y прочитал stdin"
[[ "$out" == "true true 7" ]] || fail "получено: $out"
echo "  OK"

echo "[test] install.sh пишет FEATURE_TELEGRAM_ENABLED после применения сценария"
scenario_line="$(grep -n 'apply_wiz_scenario_preset' "$ROOT_DIR/install.sh" | head -1 | cut -d: -f1)"
telegram_line="$(grep -n 'env_set FEATURE_TELEGRAM_ENABLED' "$ROOT_DIR/install.sh" | head -1 | cut -d: -f1)"
[[ -n "$scenario_line" && -n "$telegram_line" ]] || fail "не найдены строки сценария/Telegram"
[[ "$scenario_line" -lt "$telegram_line" ]] || fail "FEATURE_TELEGRAM_ENABLED должен идти после сценария"
echo "  OK"

VENV_PY="$ROOT_DIR/backend/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "[test] seed-wizard-db.py: пропуск — нет venv"
else
  DB="$TMP/wizard.db"
  seed() {
    DATABASE_URL="sqlite:///$DB" "$@" "$VENV_PY" "$ROOT_DIR/scripts/seed-wizard-db.py" \
      >"$TMP/seed.log" 2>&1 || {
      cat "$TMP/seed.log" >&2
      fail "seed-wizard-db.py упал"
    }
  }
  values() {
    "$VENV_PY" - "$DB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
rows = dict(con.execute("select key, value from app_settings"))
print(rows.get("telegram_notify_enabled", "-"), rows.get("backup_auto_enabled", "-"), rows.get("backup_auto_days", "-"))
PY
  }

  echo "[test] seed: «выключить» и Telegram без токена не включают уведомления"
  seed env WIZ_TELEGRAM_ENABLED=false WIZ_AUTO_BACKUP_ENABLED=false WIZ_AUTO_BACKUP_DAYS=7
  [[ "$(values)" == "- false 7" ]] || fail "получено: $(values)"
  echo "  OK"

  echo "[test] seed: «свой срок» пишет дни, Telegram с токеном включает уведомления"
  seed env WIZ_TELEGRAM_ENABLED=true WIZ_TELEGRAM_BOT_TOKEN=123:abc \
    WIZ_AUTO_BACKUP_ENABLED=true WIZ_AUTO_BACKUP_DAYS=30
  [[ "$(values)" == "true true 30" ]] || fail "получено: $(values)"
  echo "  OK"

  echo "[test] seed: Telegram без токена оставляет уведомления выключенными"
  rm -f "$DB"
  seed env WIZ_TELEGRAM_ENABLED=true WIZ_AUTO_BACKUP_ENABLED=true WIZ_AUTO_BACKUP_DAYS=7
  [[ "$(values)" == "- true 7" ]] || fail "получено: $(values)"
  echo "  OK"
fi

echo "All install wizard services tests passed."
