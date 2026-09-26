#!/usr/bin/env bash
# certbot standalone на время работы снимает NAT порта 80. Возвращать нужно ровно снятые
# правила: полный откат снимка iptables стёр бы правила, добавленные за это время,
# а прерванный certbot не должен оставлять сервер без перенаправления порта 80.
# Правила iptables и тела подмен — строки с буквальными кавычками.
# shellcheck disable=SC2089,SC2090
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export STATE="$TMP/prerouting" LOG="$TMP/calls.log"

R1='-i eth0 -p tcp -m tcp --dport 80 -j DNAT --to-destination 10.0.0.2:80'
R2='-i eth0 -p udp -m udp --dport 53 -j DNAT --to-destination 10.0.0.2'
R3='-i eth01 -p tcp -m tcp --dport 80 -j REDIRECT --to-ports 81'
R4='-i eth0 -p tcp -m tcp --dport 8080 -j REDIRECT --to-ports 81'
R5='-i eth0 -p tcp -m tcp --dport 80 -m comment --comment "az redirect" -j REDIRECT --to-ports 3128'
R6='-i eth0 -p udp -m udp --dport 80 -j DNAT --to-destination 10.0.0.2'
CONCURRENT='-i wg0 -j ACCEPT'
export R1 R2 R3 R4 R5 R6 CONCURRENT

# Подмена iptables, iptables-restore, ip и certbot: тест не трогает файрвол сервера.
# shellcheck disable=SC2016
FAKES='
ip() { echo "default via 192.0.2.1 dev eth0 proto dhcp src 192.0.2.10 metric 100"; }
iptables() {
  echo "iptables $*" >>"$LOG"
  [[ "$*" == "-t nat -S PREROUTING" ]] || return 2
  echo "-P PREROUTING ACCEPT"
  sed "s/^/-A PREROUTING /" "$STATE"
}
iptables-restore() {
  local input line new="$STATE.new" n
  input="$(cat)"
  echo "iptables-restore $* <<$(tr "\n" "|" <<<"$input")" >>"$LOG"
  [[ "${1:-}" == --noflush ]] || { echo "restore без --noflush сбросил бы таблицу" >&2; return 1; }
  [[ "${FAIL_RESTORE:-0}" == 1 ]] && return 1
  cp "$STATE" "$new"
  while IFS= read -r line; do
    case "$line" in
      "*nat" | COMMIT | "") ;;
      "-D PREROUTING "*)
        n="$(grep -nxF -- "${line#-D PREROUTING }" "$new" | head -1 | cut -d: -f1)"
        [[ -n "$n" ]] || return 1
        sed -i "${n}d" "$new"
        ;;
      "-I PREROUTING "*)
        line="${line#-I PREROUTING }"
        n="${line%% *}"
        (( n <= $(wc -l <"$new") + 1 )) || return 1
        { head -n $((n - 1)) "$new"; printf "%s\n" "${line#* }"; tail -n +"$n" "$new"; } >"$new.2"
        mv "$new.2" "$new"
        ;;
      *) return 1 ;;
    esac
  done <<<"$input"
  mv "$new" "$STATE"
}
certbot() {
  echo "certbot $*" >>"$LOG"
  cp "$STATE" "$STATE.during"
  [[ "${CONCURRENT_ADD:-0}" == 1 ]] && echo "$CONCURRENT" >>"$STATE"
  [[ "${CONCURRENT_READD:-0}" == 1 ]] && echo "$R1" >>"$STATE"
  [[ "${CONCURRENT_FLUSH:-0}" == 1 ]] && : >"$STATE"
  [[ "${CERTBOT_KILL:-0}" == 1 ]] && kill -TERM "$BASHPID"
  return "${CERTBOT_RC:-0}"
}
'
export FAKES

# run <команда>: библиотека в отдельном bash, чтобы проверять и выход по сигналу.
run() {
  bash -c '
    set -euo pipefail
    ENV_FILE=/dev/null
    source "$1/scripts/nginx-common.sh"
    eval "$FAKES"
    eval "$2"
  ' bash "$ROOT_DIR" "$1"
}

reset() {
  printf '%s\n' "$R1" "$R2" "$R3" "$R4" "$R5" "$R6" >"$STATE"
  rm -f "$STATE.during"
  : >"$LOG"
}

fail() {
  echo "  FAIL $*" >&2
  echo "  state:" >&2
  sed 's/^/    /' "$STATE" >&2
  echo "  calls:" >&2
  sed 's/^/    /' "$LOG" >&2
  exit 1
}

original() { printf '%s\n' "$R1" "$R2" "$R3" "$R4" "$R5" "$R6"; }

echo "[test] на время certbot снимаются только правила порта 80 внешнего интерфейса"
reset
run 'nginx_certbot_standalone certonly --standalone -d panel.example.com' >/dev/null 2>&1 || fail "certbot не прошёл"
[[ "$(cat "$STATE.during")" == "$(printf '%s\n' "$R2" "$R3" "$R4" "$R6")" ]] || fail "во время certbot: $(tr '\n' '|' <"$STATE.during")"
[[ "$(cat "$STATE")" == "$(original)" ]] || fail "правила не вернулись на свои места"
grep -q "^certbot certonly --standalone -d panel.example.com$" "$LOG" || fail "certbot вызван не с теми аргументами"
echo "  OK"

echo "[test] правила, добавленные во время certbot, сохраняются"
reset
CONCURRENT_ADD=1 run 'nginx_certbot_standalone certonly' >/dev/null 2>&1 || fail "certbot не прошёл"
[[ "$(cat "$STATE")" == "$(original; echo "$CONCURRENT")" ]] || fail "новое правило потеряно или порядок нарушен"
echo "  OK"

echo "[test] правило, заново добавленное во время certbot, не дублируется"
reset
CONCURRENT_READD=1 run 'nginx_certbot_standalone certonly' >/dev/null 2>&1 || fail "certbot не прошёл"
[[ "$(grep -cxF -- "$R1" "$STATE")" == 1 ]] || fail "правило задублировано"
[[ "$(grep -cxF -- "$R5" "$STATE")" == 1 ]] || fail "снятое правило не вернулось"
echo "  OK"

echo "[test] цепочка укоротилась во время certbot: правила всё равно возвращаются"
reset
CONCURRENT_FLUSH=1 run 'nginx_certbot_standalone certonly' >/dev/null 2>&1 || fail "certbot не прошёл"
[[ "$(cat "$STATE")" == "$(printf '%s\n' "$R1" "$R5")" ]] || fail "правила не вернулись в пустую цепочку"
echo "  OK"

echo "[test] сбой certbot: правила возвращаются, код ошибки передаётся"
reset
set +e
CERTBOT_RC=3 run 'nginx_certbot_standalone certonly' >/dev/null 2>&1
rc=$?
set -e
[[ "$rc" == 3 ]] || fail "код certbot потерян: $rc"
[[ "$(cat "$STATE")" == "$(original)" ]] || fail "после сбоя правила не вернулись"
echo "  OK"

echo "[test] прерывание во время certbot: правила возвращаются, прежний EXIT-trap выполняется"
reset
set +e
CERTBOT_KILL=1 run 'trap "echo prev-exit >>\"$LOG\"" EXIT; nginx_certbot_standalone certonly; echo after >>"$LOG"' >/dev/null 2>&1
set -e
[[ "$(cat "$STATE")" == "$(original)" ]] || fail "после прерывания правила не вернулись"
grep -qx "prev-exit" "$LOG" || fail "прежний EXIT-trap не выполнен"
! grep -qx "after" "$LOG" || fail "скрипт продолжился после SIGTERM"
echo "  OK"

echo "[test] после certbot прежний EXIT-trap на месте"
reset
out="$(run 'trap "echo mine" EXIT; nginx_certbot_standalone certonly >/dev/null 2>&1; trap -p EXIT' 2>/dev/null)"
grep -q "echo mine" <<<"$out" || fail "EXIT-trap не восстановлен: $out"
out="$(run 'nginx_certbot_standalone certonly >/dev/null 2>&1; trap -p EXIT' 2>/dev/null)"
[[ -z "$out" ]] || fail "после certbot остался EXIT-trap: $out"
echo "  OK"

echo "[test] повторное восстановление не дублирует правила"
reset
run 'nginx_certbot_standalone certonly >/dev/null 2>&1; nginx_restore_port80_nat' >/dev/null 2>&1 || fail "сбой"
[[ "$(cat "$STATE")" == "$(original)" ]] || fail "правила задублированы"
echo "  OK"

echo "[test] сбой восстановления: предупреждение с командами для ручного возврата"
reset
run 'nginx_temp_clear_port80_nat; FAIL_RESTORE=1 nginx_restore_port80_nat' >/dev/null 2>"$TMP/err" || true
grep -qF -- "iptables -t nat -A PREROUTING $R1" "$TMP/err" || fail "нет команды для ручного возврата: $(cat "$TMP/err")"
grep -qF -- "iptables -t nat -A PREROUTING $R5" "$TMP/err" || fail "нет команды для правила с комментарием"
echo "  OK"

echo "[test] нет правил порта 80 — iptables-restore не вызывается"
printf '%s\n' "$R2" "$R4" >"$STATE"
: >"$LOG"
run 'nginx_certbot_standalone certonly' >/dev/null 2>&1 || fail "certbot не прошёл"
! grep -q "^iptables-restore" "$LOG" || fail "лишний вызов iptables-restore"
echo "  OK"

echo "[test] настоящий iptables в отдельном сетевом namespace (пропуск без root и unshare)"
if command -v iptables >/dev/null 2>&1 && unshare --net true 2>/dev/null; then
  unshare --net bash -c '
    set -euo pipefail
    ip link add eth0 type dummy
    ip link set eth0 up
    ip addr add 192.0.2.10/24 dev eth0
    ip route add default via 192.0.2.1 dev eth0
    iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 80 -j DNAT --to-destination 10.0.0.2:80
    iptables -t nat -A PREROUTING -i eth0 -p udp --dport 53 -j DNAT --to-destination 10.0.0.2
    iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 80 -m comment --comment "az \"redirect\"" -j REDIRECT --to-ports 3128
    before="$(iptables -t nat -S PREROUTING)"
    ENV_FILE=/dev/null
    source "$1/scripts/nginx-common.sh"
    certbot() {
      ! iptables -t nat -S PREROUTING | grep -q -- "--dport 80 " || exit 1
      iptables -t nat -A PREROUTING -i wg0 -j ACCEPT
    }
    nginx_certbot_standalone certonly >/dev/null 2>&1
    [[ "$(iptables -t nat -S PREROUTING)" == "$before"$'"'"'\n-A PREROUTING -i wg0 -j ACCEPT'"'"' ]]
  ' bash "$ROOT_DIR" || fail "настоящий iptables: правила не вернулись в прежнем порядке"
  echo "  OK"
else
  echo "  SKIP"
fi

echo "All certbot NAT checks passed."
