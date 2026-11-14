#!/usr/bin/env bash
# --server-only --only=… / FU_ONLY: выполняются только выбранные шаги, пустой и неизвестный список
# отклоняются до изменений. Шаги подменены счётчиками; установка и systemd — во временном каталоге.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
INSTALL="$TMP/install"
mkdir -p "$INSTALL" "$TMP/units"
export CALLS="$TMP/calls.log"
export FU_TEST_STATE="$TMP/state"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run [args…]: full_update_main с заглушками шагов. RUN_FU_ONLY — значение FU_ONLY для проверки env-варианта;
# итог — $TMP/out и RC.
RUN_FU_ONLY=""
run() {
  local -a env_args=()
  : >"$CALLS"
  : >"$FU_TEST_STATE"
  if [[ -n "$RUN_FU_ONLY" ]]; then
    env_args+=("FU_ONLY=$RUN_FU_ONLY")
  fi
  set +e
  env -u LC_ALL -u LC_CTYPE -u SSH_CONNECTION LANG=C.UTF-8 NO_COLOR=1 \
    INSTALL_DIR="$INSTALL" FU_TEST_STATE="$FU_TEST_STATE" "${env_args[@]}" \
    bash -c '
    source "$1/scripts/full-update.sh"
    shift
    FU_STATE="$FU_TEST_STATE"
    require_root() { :; }
    menu_mode() { echo systemd; }
    fu_finish() { :; }
    fu_sync_scenario_db() { :; }
    fu_step_apt() { echo apt >>"$CALLS"; fu_row apt ok; }
    fu_step_systemd() { echo systemd >>"$CALLS"; fu_row systemd ok; }
    fu_step_nginx() { echo nginx >>"$CALLS"; fu_row nginx ok; }
    fu_step_firewall() { echo firewall >>"$CALLS"; fu_row firewall ok; }
    fu_step_ddns() { echo ddns >>"$CALLS"; fu_row ddns ok; }
    full_update_main "$@"
  ' bash "$ROOT_DIR" "$@" >"$TMP/out" 2>&1
  RC=$?
  set -e
  RUN_FU_ONLY=""
}

calls() { tr '\n' ';' <"$CALLS"; }

echo "[test] --only=nginx: только nginx"
run --server-only --only=nginx
[[ "$RC" -eq 0 && "$(calls)" == "nginx;" ]] && ok "выполнен только nginx" || bad "код $RC, вызовы: $(calls); $(cat "$TMP/out")"

echo "[test] --only nginx,firewall: оба шага в порядке списка"
run --server-only --only nginx,firewall
[[ "$RC" -eq 0 && "$(calls)" == "nginx;firewall;" ]] && ok "nginx, firewall" || bad "код $RC, вызовы: $(calls); $(cat "$TMP/out")"

echo "[test] FU_ONLY=apt,ddns с --server-only"
RUN_FU_ONLY="apt,ddns"
run --server-only
[[ "$RC" -eq 0 && "$(calls)" == "apt;ddns;" ]] && ok "выбраны apt и ddns" || bad "код $RC, вызовы: $(calls); $(cat "$TMP/out")"

echo "[test] без выбора: все пять шагов"
run --server-only
[[ "$RC" -eq 0 && "$(calls)" == "apt;systemd;nginx;firewall;ddns;" ]] && ok "все шаги" \
  || bad "код $RC, вызовы: $(calls); $(cat "$TMP/out")"

echo "[test] неизвестный шаг: код 2, шаги не запускаются"
run --server-only --only=nginx,bogus
[[ "$RC" -eq 2 && "$(calls)" == "" ]] && grep -qF "Неизвестный шаг: bogus" "$TMP/out" \
  && ok "неизвестный шаг отклонён" || bad "код $RC, вызовы: $(calls); $(cat "$TMP/out")"

echo "[test] пустой --only=: код 2, шаги не запускаются"
run --server-only --only=
[[ "$RC" -eq 2 && "$(calls)" == "" ]] && grep -qF "Пустой список шагов" "$TMP/out" \
  && ok "пустой список отклонён" || bad "код $RC, вызовы: $(calls); $(cat "$TMP/out")"

echo "[test] --only без --server-only: код 2"
run --only=nginx
[[ "$RC" -eq 2 && "$(calls)" == "" ]] && grep -qF "только с --server-only" "$TMP/out" \
  && ok "выбор только для --server-only" || bad "код $RC, вызовы: $(calls); $(cat "$TMP/out")"

echo "[test] дубли в списке выполняются один раз"
run --server-only --only=nginx,nginx
[[ "$RC" -eq 0 && "$(calls)" == "nginx;" ]] && ok "дубль отброшен" || bad "код $RC, вызовы: $(calls); $(cat "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
