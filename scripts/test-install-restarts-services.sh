#!/usr/bin/env bash
# Повторный install.sh должен перезапускать уже работающие сервисы: systemctl start на запущенном сервисе
# ничего не делает, и панель, node agent и proxy agent остаются на старом коде и настройках.
# При публикации через nginx панель перезапускается один раз — после настройки публикации.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export LOG="$TMP/calls.log"

FNS="$(for fn in run_install_flow start_daemon start_node_via_systemd restart_services_after_nginx; do
  sed -n "/^${fn}() {/,/^}/p" "$ROOT_DIR/install.sh"
done)"

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run_flow <WITH_SYSTEMD> <WITH_DAEMON> <WIZ_NGINX_MODE>: run_install_flow, все шаги установки — заглушки
run_flow() {
  : >"$LOG"
  set +e
  WITH_SYSTEMD="$1" WITH_DAEMON="$2" WIZ_NGINX_MODE="$3" bash -c '
    set -euo pipefail
    systemctl() { echo "systemctl $*" >>"$LOG"; }
    log() { :; }
    warn() { echo "WARN $*" >&2; }
    install_controller_selected() { return 0; }
    install_node_selected() { return 0; }
    install_proxy_selected() { return 0; }
    for fn in install_set_step check_os resolve_project_dir run_wizard_if_needed check_antizapret \
      install_preflight_ports install_system_deps ensure_executable_scripts setup_env setup_node_env \
      setup_proxy_env setup_backend seed_admin_user_from_env seed_wizard_db_settings setup_frontend \
      setup_runtime_dirs setup_systemd setup_ddns_if_selected disable_openvpn_backup_tcp_if_port_conflict \
      setup_nginx_if_selected setup_firewall_if_selected \
      setup_node_agent_systemd setup_proxy_agent_systemd verify_controller_running setup_console_command print_post_install; do
      eval "${fn}() { :; }"
    done
    GENERATED_NODE_KEY=key
    eval "$1"
    run_install_flow
  ' bash "$FNS" 2>"$TMP/err"
  rc=$?
  set -e
}

EXPECTED="systemctl restart adminpanelaz
systemctl restart adminpanelaz-node
systemctl restart adminpanelaz-proxy"

for mode in "true false none systemd" "false true none daemon" "true false le systemd+nginx"; do
  read -r with_systemd with_daemon nginx_mode name <<<"$mode"
  echo "[test] --with-$name: панель, node agent и proxy agent перезапускаются по одному разу"
  run_flow "$with_systemd" "$with_daemon" "$nginx_mode"
  [[ "$rc" -eq 0 ]] && ok "установка прошла" || bad "код $rc: $(cat "$TMP/err")"
  ! grep -q "command not found" "$TMP/err" && ok "все шаги заглушены" || bad "неизвестный шаг: $(grep "command not found" "$TMP/err")"
  [[ "$(cat "$LOG")" == "$EXPECTED" ]] && ok "systemctl restart для трёх сервисов" || bad "вызовы: $(tr '\n' ';' <"$LOG")"
done

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
