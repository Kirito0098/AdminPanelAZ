#!/usr/bin/env bash
# --proxy-only / --node-only задают тип установки до мастера: мастер не должен спрашивать тип заново,
# а с -y — подменять его на «Панель + локальный AntiZapret» и требовать /root/antizapret (issue #19).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

extract() {
  local file="$1" fn
  shift
  for fn in "$@"; do
    sed -n "/^${fn}() {/,/^}/p" "$file"
  done
}

WIZARD_FNS="$(extract "$ROOT_DIR/scripts/install-wizard.sh" wiz_set_total_steps wizard_ask_install_type \
  wizard_check_antizapret wizard_configure_antizapret)"

fail() {
  echo "  FAIL $*" >&2
  exit 1
}

# run_type <WIZ_INSTALL_TYPE до мастера> <WIZ_ACCEPT_DEFAULTS> [ответ на вопрос о типе]
# Печатает «тип require_antizapret prompted», где prompted — задавался ли вопрос о типе.
run_type() {
  WIZ_INSTALL_TYPE="$1" WIZ_ACCEPT_DEFAULTS="$2" ANSWER="${3:-}" bash -c '
    set -euo pipefail
    wiz_step() { :; }
    ui_info_box() { :; }
    print_info() { :; }
    die() { echo "DIE $*"; exit 1; }
    prompted=false
    wiz_prompt_choice() { prompted=true; REPLY="$ANSWER"; }
    WIZ_REQUIRE_ANTIZAPRET=true
    eval "$1"
    WIZ_ANTIZAPRET_PATH=/nonexistent-antizapret
    wizard_ask_install_type >/dev/null
    echo "$WIZ_INSTALL_TYPE $WIZ_REQUIRE_ANTIZAPRET $prompted"
  ' bash "$WIZARD_FNS" | tail -1
}

echo "[test] --proxy-only -y: тип proxy, AntiZapret не нужен, вопроса нет"
[[ "$(run_type proxy true)" == "proxy false false" ]] || fail "получено: $(run_type proxy true)"
echo "  OK"

echo "[test] --proxy-only без -y: вопрос о типе не задаётся"
[[ "$(run_type proxy false 2)" == "proxy false false" ]] || fail "получено: $(run_type proxy false 2)"
echo "  OK"

echo "[test] --node-only -y и без -y: тип node, вопроса нет"
[[ "$(run_type node true)" == "node true false" ]] || fail "получено: $(run_type node true)"
[[ "$(run_type node false 1)" == "node true false" ]] || fail "получено: $(run_type node false 1)"
echo "  OK"

echo "[test] без флага -y по-прежнему выбирает «Панель + локальный AntiZapret»"
[[ "$(run_type controller true)" == "controller true false" ]] || fail "получено: $(run_type controller true)"
echo "  OK"

echo "[test] без флага мастер спрашивает тип, ответ 4 — proxy"
[[ "$(run_type controller false 4)" == "proxy false true" ]] || fail "получено: $(run_type controller false 4)"
echo "  OK"

echo "[test] --proxy-only -y без /root/antizapret не прерывает установку"
out="$(WIZ_INSTALL_TYPE=proxy WIZ_ACCEPT_DEFAULTS=true bash -c '
  set -euo pipefail
  wiz_step() { :; }
  ui_info_box() { :; }
  print_info() { :; }
  die() { echo "DIE $*"; exit 1; }
  wiz_prompt_choice() { REPLY=2; }
  WIZ_REQUIRE_ANTIZAPRET=true
  eval "$1"
  wizard_check_antizapret() { [[ "$WIZ_REQUIRE_ANTIZAPRET" == true ]] && die "нужен AntiZapret"; return 0; }
  wizard_ask_install_type >/dev/null
  wizard_configure_antizapret >/dev/null
  echo "continued"
' bash "$WIZARD_FNS" | tail -1)"
[[ "$out" == continued ]] || fail "установка прервана: $out"
echo "  OK"

echo "All install wizard type flag checks passed."
