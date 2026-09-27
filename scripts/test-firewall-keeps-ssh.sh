#!/usr/bin/env bash
# Настройка firewall не должна отрезать SSH: закрыть порт, на котором слушает sshd, или
# включить ufw (политика deny) без разрешения SSH.
# Переменные вроде SSH_CONNECTION читают firewall-setup.sh и подменённые утилиты.
# shellcheck disable=SC2034
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

LOG="$TMP_DIR/calls.log"
ADDED="$TMP_DIR/ufw-added"

# shellcheck source=scripts/firewall-setup.sh
source "$ROOT_DIR/scripts/firewall-setup.sh"
set +e

# Функции перекрывают настоящие утилиты: тест не может изменить файрвол сервера.
TOOL=ufw
UFW_STATE=inactive
SSHD_PORTS=""
SS_SSHD_PORTS=""
SOCKET_PORTS=""
SOCKET_ACTIVE=true
firewall_detect_tool() { echo "$TOOL"; }
ufw() {
  echo "ufw $*" >>"$LOG"
  case "$1" in
    status) echo "Status: $UFW_STATE" ;;
    show)
      echo "Added user rules (see 'ufw status' for running firewall):"
      cat "$ADDED"
      ;;
  esac
  return 0
}
iptables() {
  echo "iptables $*" >>"$LOG"
  [[ "$1" == -C ]] && return 1
  return 0
}
netfilter-persistent() { return 0; }
firewall_persist_iptables_rules() { :; }
# Socket-активация (Ubuntu 22.10+): порт слушает systemd, в ss процесса sshd не видно.
systemctl() {
  local p
  case "$*" in
    "is-active --quiet ssh.socket") [[ "$SOCKET_ACTIVE" == true ]] ;;
    "show -p Listen --value ssh.socket")
      for p in $SOCKET_PORTS; do
        echo "0.0.0.0:$p (Stream)"
        echo "[::]:$p (Stream)"
      done
      ;;
    *) return 0 ;;
  esac
}
sshd() {
  [[ "$1" == -T && -n "$SSHD_PORTS" ]] || return 1
  local p
  for p in $SSHD_PORTS; do echo "port $p"; done
  echo "addressfamily any"
}
ss() {
  local p
  echo "LISTEN 0 4096 127.0.0.53%lo:53 0.0.0.0:* users:((\"systemd-resolve\",pid=5,fd=14))"
  for p in $SS_SSHD_PORTS; do
    echo "LISTEN 0 128 0.0.0.0:$p 0.0.0.0:* users:((\"sshd\",pid=1,fd=3))"
    echo "LISTEN 0 128 [::]:$p [::]:* users:((\"sshd\",pid=1,fd=4))"
  done
}

reset() {
  : >"$LOG"
  : >"$ADDED"
  TOOL=ufw UFW_STATE=inactive SSHD_PORTS="" SS_SSHD_PORTS="" SOCKET_PORTS="" SOCKET_ACTIVE=true
  unset SSH_CONNECTION FIREWALL_ENABLE_UFW
}

fail() {
  echo "  FAIL $*" >&2
  echo "  calls:" >&2
  sed 's/^/    /' "$LOG" >&2
  exit 1
}

line_of() { grep -nxF -- "$1" "$LOG" | head -1 | cut -d: -f1; }

echo "[test] порты SSH: текущая сессия, sshd -T, ss, по умолчанию 22"
reset
SSH_CONNECTION="203.0.113.5 50000 198.51.100.1 2222" SSHD_PORTS="22 2222"
[[ "$(firewall_ssh_ports | tr '\n' ' ')" == "22 2222 " ]] || fail "ожидались 22 и 2222: [$(firewall_ssh_ports | tr '\n' ' ')]"
reset
SSH_CONNECTION="203.0.113.5 50000 198.51.100.1 2022"
[[ "$(firewall_ssh_ports | tr '\n' ' ')" == "2022 " ]] || fail "порт текущей сессии: [$(firewall_ssh_ports | tr '\n' ' ')]"
reset
SS_SSHD_PORTS="2200"
[[ "$(firewall_ssh_ports | tr '\n' ' ')" == "2200 " ]] || fail "порт из ss: [$(firewall_ssh_ports | tr '\n' ' ')]"
reset
SOCKET_PORTS="2345"
[[ "$(firewall_ssh_ports | tr '\n' ' ')" == "2345 " ]] || fail "порт из ssh.socket: [$(firewall_ssh_ports | tr '\n' ' ')]"
reset
SOCKET_PORTS="22" SOCKET_ACTIVE=false SS_SSHD_PORTS="2200"
[[ "$(firewall_ssh_ports | tr '\n' ' ')" == "2200 " ]] || fail "выключенный ssh.socket учтён: [$(firewall_ssh_ports | tr '\n' ' ')]"
reset
[[ "$(firewall_ssh_ports)" == 22 ]] || fail "по умолчанию 22: [$(firewall_ssh_ports)]"
echo "  OK"

echo "[test] firewall не закрывает порт SSH"
for tool in ufw iptables; do
  reset
  TOOL=$tool SSHD_PORTS="22"
  firewall_apply_rules 22 0 443 80 false true "" 2>"$TMP_DIR/err" && fail "$tool: backend на порту SSH принят"
  grep -q "SSH" "$TMP_DIR/err" || fail "$tool: нет объяснения про SSH"
  ! grep -Eq "^(ufw (allow|deny|--force)|iptables -[AI])" "$LOG" || fail "$tool: правила применены до отказа"
  reset
  TOOL=$tool SSH_CONNECTION="203.0.113.5 50000 198.51.100.1 2222"
  firewall_apply_rules 0 2222 443 80 true false "203.0.113.10" 2>/dev/null && fail "$tool: node agent на порту SSH принят"
  reset
  TOOL=$tool SS_SSHD_PORTS="9101"
  firewall_apply_rules 0 0 443 80 false false "" true 9101 2>/dev/null && fail "$tool: proxy agent на порту SSH принят"
  reset
  TOOL=$tool SSHD_PORTS="22"
  firewall_apply_rules 8000 9100 443 80 true true "203.0.113.10" >/dev/null 2>&1 || fail "$tool: обычные порты отклонены"
  reset
  TOOL=$tool SSHD_PORTS="22"
  firewall_apply_rules 0 0 22 0 false true "" >/dev/null 2>&1 || fail "$tool: открытие порта SSH не должно отклоняться"
done
echo "  OK"

echo "[test] включение ufw: сначала SSH и порты панели, потом enable"
reset
SSHD_PORTS="22" SSH_CONNECTION="203.0.113.5 50000 198.51.100.1 2222"
FIREWALL_ENABLE_UFW=true firewall_apply_rules 8000 0 443 80 false true "" >/dev/null 2>&1 || fail "правила не применены"
enable_at="$(line_of "ufw --force enable")"
[[ -n "$enable_at" ]] || fail "ufw не включён"
for rule in "ufw allow 22/tcp comment SSH (AdminPanelAZ)" "ufw allow 2222/tcp comment SSH (AdminPanelAZ)" \
    "ufw allow 443/tcp comment AdminPanelAZ HTTPS" "ufw deny 8000/tcp comment AdminPanelAZ backend"; do
  at="$(line_of "$rule")"
  [[ -n "$at" && "$at" -lt "$enable_at" ]] || fail "[$rule] не добавлено до включения ufw"
done
echo "  OK"

echo "[test] неактивный ufw без включения: SSH всё равно разрешается заранее"
reset
SSHD_PORTS="22"
firewall_apply_rules 8000 0 443 80 false true "" >/dev/null 2>&1
grep -qxF "ufw allow 22/tcp comment SSH (AdminPanelAZ)" "$LOG" || fail "SSH не разрешён"
! grep -qxF "ufw --force enable" "$LOG" || fail "ufw включён без FIREWALL_ENABLE_UFW"
echo "  OK"

echo "[test] своё правило SSH пользователя не расширяется"
for rule in "ufw allow from 203.0.113.0/24 to any port 22 proto tcp" "ufw limit OpenSSH" "ufw allow 22/tcp" "ufw limit ssh"; do
  reset
  SSHD_PORTS="22"
  echo "$rule" >"$ADDED"
  FIREWALL_ENABLE_UFW=true firewall_apply_rules 8000 0 443 80 false true "" >/dev/null 2>&1
  ! grep -q "^ufw allow 22/tcp comment SSH" "$LOG" || fail "SSH разрешён поверх [$rule]"
done
for rule in "ufw allow from 10.0.0.22 to any port 443 proto tcp" "ufw allow from 203.0.113.0/24 to any port 2222 proto tcp"; do
  reset
  SSHD_PORTS="22"
  echo "$rule" >"$ADDED"
  firewall_apply_rules 8000 0 443 80 false true "" >/dev/null 2>&1
  grep -q "^ufw allow 22/tcp comment SSH" "$LOG" || fail "[$rule] ошибочно принято за правило SSH"
done
echo "  OK"

echo "[test] активный ufw: SSH не трогаем"
reset
SSHD_PORTS="22" UFW_STATE=active
FIREWALL_ENABLE_UFW=true firewall_apply_rules 8000 0 443 80 false true "" >/dev/null 2>&1
! grep -q "^ufw allow 22/tcp" "$LOG" || fail "на активном ufw добавлено правило SSH"
! grep -qxF "ufw --force enable" "$LOG" || fail "активный ufw включён повторно"
echo "  OK"

echo "All firewall SSH checks passed."
