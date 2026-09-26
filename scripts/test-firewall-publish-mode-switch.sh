#!/usr/bin/env bash
# Смена режима публикации (Nginx ↔ прямой доступ) должна менять доступ к порту панели:
# правило прежнего режима, оставшееся выше в цепочке, перекрывало бы новое.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

RULES="$TMP_DIR/rules"
: >"$RULES"

# shellcheck source=scripts/firewall-setup.sh
source "$ROOT_DIR/scripts/firewall-setup.sh"
set +e

# Функции перекрывают настоящие iptables/ufw: тест не может изменить файрвол сервера.
iptables() {
  local op="$1" chain="$2"
  shift 2
  [[ "$chain" == INPUT ]] || return 2
  local rule="$*"
  case "$op" in
    -C) grep -qxF -- "$rule" "$RULES" ;;
    -A) printf '%s\n' "$rule" >>"$RULES" ;;
    -I) { printf '%s\n' "$rule"; cat "$RULES"; } >"$RULES.new" && mv "$RULES.new" "$RULES" ;;
    -D)
      local n
      n="$(grep -nxF -- "$rule" "$RULES" | head -1 | cut -d: -f1)"
      [[ -n "$n" ]] || return 1
      sed -i "${n}d" "$RULES"
      ;;
    *) return 2 ;;
  esac
}

# Как настоящий ufw в худшем случае: правило с другим действием для того же порта добавляется,
# а не заменяет старое; каждое правило идёт парой IPv4 + (v6), и номера сдвигаются после удаления.
ufw() {
  case "$1" in
    status)
      echo "Status: active"
      if [[ "${2:-}" == numbered ]]; then
        echo
        echo "     To                         Action      From"
        echo "     --                         ------      ----"
        local i=0 port action from
        while IFS=$'\t' read -r port action; do
          i=$((i + 1))
          from="Anywhere"
          [[ "$port" == *"(v6)" ]] && from="Anywhere (v6)"
          printf '[%2d] %-26s %-11s %s\n' "$i" "$port" "$action IN" "$from"
        done <"$RULES"
      fi
      ;;
    allow | deny)
      local action="${1^^}" port="$2" v
      [[ "$port" == */tcp ]] || return 0
      for v in "$port" "$port (v6)"; do
        grep -qxF "$v"$'\t'"$action" "$RULES" || printf '%s\t%s\n' "$v" "$action" >>"$RULES"
      done
      ;;
    --force)
      [[ "$2" == delete ]] || return 2
      sed -i "${3}d" "$RULES"
      ;;
    reload | enable) return 0 ;;
    *) return 0 ;;
  esac
}

netfilter-persistent() { return 0; }

fail() {
  echo "  FAIL $*" >&2
  echo "  rules:" >&2
  sed 's/^/    /' "$RULES" >&2
  exit 1
}

# Первое подходящее правило для порта решает судьбу пакета с внешнего адреса.
iptables_verdict() {
  local port="$1" line
  while IFS= read -r line; do
    if [[ "$line" == "-p tcp --dport $port "* ]]; then
      case "$line" in
        *"-j ACCEPT") echo open; return ;;
        *"-j DROP") echo closed; return ;;
      esac
    fi
  done <"$RULES"
  echo none
}

ufw_family_verdict() {
  local want_port="$1" rport action
  while IFS=$'\t' read -r rport action; do
    if [[ "$rport" == "$want_port" ]]; then
      [[ "$action" == ALLOW ]] && echo open || echo closed
      return
    fi
  done <"$RULES"
  echo none
}

ufw_verdict() {
  local v4 v6
  v4="$(ufw_family_verdict "$1/tcp")"
  v6="$(ufw_family_verdict "$1/tcp (v6)")"
  [[ "$v4" == "$v6" ]] && echo "$v4" || echo "v4=$v4,v6=$v6"
}

expect() {
  local tool="$1" port="$2" want="$3" what="$4" got
  got="$("${tool}_verdict" "$port")"
  [[ "$got" == "$want" ]] || fail "$what: порт $port должен быть $want, а он $got"
}

for tool in iptables ufw; do
  : >"$RULES"
  eval "firewall_detect_tool() { echo $tool; }"

  echo "[test] $tool: прямая публикация → Nginx закрывает порт панели"
  firewall_apply_publish_mode http_direct 8000 443 80 >/dev/null 2>&1
  expect "$tool" 8000 open "прямая публикация"
  firewall_apply_publish_mode nginx_le 8000 443 80 >/dev/null 2>&1
  expect "$tool" 8000 closed "после перехода на Nginx"
  expect "$tool" 443 open "после перехода на Nginx"
  echo "  OK"

  echo "[test] $tool: Nginx → прямая публикация открывает порт панели"
  firewall_apply_publish_mode uvicorn_le 8000 443 80 >/dev/null 2>&1
  expect "$tool" 8000 open "после возврата на прямую публикацию"
  echo "  OK"

  echo "[test] $tool: повторное применение не плодит правила"
  firewall_apply_publish_mode nginx_le 8000 443 80 >/dev/null 2>&1
  firewall_apply_publish_mode nginx_le 8000 443 80 >/dev/null 2>&1
  expect "$tool" 8000 closed "повтор Nginx"
  want_count=1
  [[ "$tool" == ufw ]] && want_count=2
  [[ "$(grep -c '8000' "$RULES")" == "$want_count" ]] || fail "правило для 8000 должно быть одно"
  echo "  OK"

  echo "[test] $tool: переустановка install.sh в прямом режиме после Nginx открывает порт"
  firewall_apply_rules 0 0 8000 0 false true "" >/dev/null 2>&1
  expect "$tool" 8000 open "установка в прямом режиме"
  echo "  OK"

  echo "[test] $tool: переустановка install.sh с Nginx после прямого режима закрывает порт"
  firewall_apply_rules 8000 0 443 80 false true "" >/dev/null 2>&1
  expect "$tool" 8000 closed "установка с Nginx"
  echo "  OK"
done

echo "[test] iptables: дубли ACCEPT от прежних версий удаляются все"
: >"$RULES"
firewall_detect_tool() { echo iptables; }
printf '%s\n' "-p tcp --dport 8000 -j ACCEPT" "-p tcp --dport 22 -j ACCEPT" "-p tcp --dport 8000 -j ACCEPT" >"$RULES"
firewall_apply_publish_mode nginx_le 8000 443 80 >/dev/null 2>&1
expect iptables 8000 closed "дубли ACCEPT"
grep -qxF -- "-p tcp --dport 22 -j ACCEPT" "$RULES" || fail "правило SSH удалено"
echo "  OK"

echo "[test] ufw: чужие правила и другие порты не трогаются"
: >"$RULES"
firewall_detect_tool() { echo ufw; }
printf '%s\t%s\n' "22/tcp" ALLOW "80008/tcp" ALLOW "8000/tcp" ALLOW "22/tcp (v6)" ALLOW "8000/tcp (v6)" ALLOW >"$RULES"
firewall_apply_publish_mode nginx_le 8000 443 80 >/dev/null 2>&1
expect ufw 8000 closed "ufw с чужими правилами"
expect ufw 22 open "SSH"
grep -qxF "80008/tcp"$'\t'"ALLOW" "$RULES" || fail "правило другого порта удалено"
echo "  OK"

echo "All firewall publish mode checks passed."
