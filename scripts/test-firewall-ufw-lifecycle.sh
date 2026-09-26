#!/usr/bin/env bash
# Правила ufw панели снимаются при удалении и на неактивном ufw, а правило SSH остаётся:
# после uninstall + install ufw уже активен, и SSH заново не разрешается.
# shellcheck disable=SC2034
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

RULES="$TMP_DIR/rules"

# shellcheck source=scripts/firewall-setup.sh
source "$ROOT_DIR/scripts/firewall-setup.sh"
set +e

# Модель ufw: строки «семейство<TAB>правило<TAB>комментарий». Как у настоящего ufw,
# status numbered пуст на неактивном ufw, номера идут сначала по IPv4, затем по (v6),
# а удаление по описанию снимает обе версии правила.
UFW_STATE=inactive
ufw_spec_display() {
  local spec="$1"
  if [[ "$spec" =~ ^(allow|deny)\ ([0-9]+/tcp)$ ]]; then
    printf '%s\t%s\tAnywhere' "${BASH_REMATCH[2]}" "${BASH_REMATCH[1]^^} IN"
  elif [[ "$spec" =~ ^(allow|deny)\ from\ ([^ ]+)\ to\ any\ port\ ([0-9]+)\ proto\ tcp$ ]]; then
    printf '%s/tcp\t%s\t%s' "${BASH_REMATCH[3]}" "${BASH_REMATCH[1]^^} IN" "${BASH_REMATCH[2]}"
  fi
}
ufw_numbered() {
  local fam spec comment to action from i=0
  for want in v4 v6; do
    while IFS=$'\t' read -r fam spec comment; do
      [[ "$fam" == "$want" ]] || continue
      i=$((i + 1))
      IFS=$'\t' read -r to action from <<<"$(ufw_spec_display "$spec")"
      [[ "$fam" == v6 ]] && to+=" (v6)" && from+=" (v6)"
      printf '[%2d] %-26s %-11s %-26s%s\n' "$i" "$to" "$action" "$from" "${comment:+ # $comment}"
    done <"$RULES"
  done
}
ufw_add() {
  local spec="$1" comment="$2" fam
  grep -q $'\t'"${spec}"$'\t' "$RULES" && return 0
  printf 'v4\t%s\t%s\n' "$spec" "$comment" >>"$RULES"
  [[ "$spec" == *" from "*.*.*.*" "* ]] || printf 'v6\t%s\t%s\n' "$spec" "$comment" >>"$RULES"
}
ufw() {
  local comment="" spec
  case "$1" in
    status)
      echo "Status: $UFW_STATE"
      if [[ "$UFW_STATE" == active && "${2:-}" == numbered ]]; then
        printf '\n     To                         Action      From\n     --                         ------      ----\n'
        ufw_numbered
      fi
      ;;
    show)
      [[ "${2:-}" == added ]] || return 2
      echo "Added user rules (see 'ufw status' for running firewall):"
      awk -F '\t' '$1 == "v4" { printf "ufw %s", $2; if ($3 != "") printf " comment '"'"'%s'"'"'", $3; print "" }' "$RULES"
      ;;
    allow | deny)
      spec="$*"
      if [[ "$spec" == *" comment "* ]]; then
        comment="${spec#* comment }"
        spec="${spec% comment *}"
      fi
      ufw_add "$spec" "$comment"
      ;;
    --force)
      [[ "$2" == enable ]] && UFW_STATE=active && return 0
      [[ "$2" == delete ]] || return 2
      shift 2
      if [[ "$*" =~ ^[0-9]+$ ]]; then
        [[ "$UFW_STATE" == active ]] || return 1
        local line
        line="$(ufw_numbered | sed -n "s/^\[ *${1}\] //p")"
        [[ -n "$line" ]] || return 1
        local n
        n="$(awk -v k="$1" -F '\t' '{ if ($1 == "v4") v4[++a] = NR; else v6[++b] = NR } END { if (k <= a) print v4[k]; else print v6[k - a] }' "$RULES")"
        sed -i "${n}d" "$RULES"
      else
        local word
        for word in "$@"; do
          [[ "$word" != *" "* ]] || return 1
        done
        spec="$*"
        grep -q $'\t'"${spec}"$'\t' "$RULES" || return 1
        awk -F '\t' -v s="$spec" '$2 != s' "$RULES" >"$RULES.new" && mv "$RULES.new" "$RULES"
      fi
      ;;
    enable) UFW_STATE=active ;;
    reload) return 0 ;;
    *) return 0 ;;
  esac
}
sshd() { return 1; }
ss() { return 0; }
netfilter-persistent() { return 0; }

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() {
  fail=$((fail + 1))
  echo "  FAIL $1" >&2
  sed 's/^/    /' "$RULES" >&2
}
check() { if eval "$1"; then ok "$2"; else bad "$2"; fi; }
has_rule() { grep -q $'\t'"$1"$'\t' "$RULES"; }

reset() {
  : >"$RULES"
  UFW_STATE="$1"
  unset SSH_CONNECTION FIREWALL_ENABLE_UFW
}

install_rules() {
  firewall_apply_ufw_rules 8000 9100 443 80 true true 203.0.113.5 true 9101 >/dev/null 2>&1
}

echo "[test] ufw неактивен, установка включает его: uninstall оставляет SSH, повторная установка не теряет его"
reset inactive
export FIREWALL_ENABLE_UFW=true
install_rules
check '[[ "$UFW_STATE" == active ]] && has_rule "allow 22/tcp"' "SSH разрешён до включения ufw"
firewall_remove_ufw_rules >/dev/null 2>&1
check 'has_rule "allow 22/tcp"' "uninstall не удалил правило SSH"
check '! grep -v "SSH (AdminPanelAZ)" "$RULES" | grep -q AdminPanelAZ' "остальные правила панели удалены (IPv4 и v6)"
install_rules
check '[[ "$(grep -c $'"'"'\tallow 22/tcp\t'"'"' "$RULES")" == 2 ]]' "после повторной установки SSH на месте, без дублей"

echo "[test] ufw неактивен и не включается: uninstall снимает правила панели"
reset inactive
install_rules
check 'has_rule "deny 8000/tcp" && has_rule "allow 443/tcp"' "правила добавлены в неактивный ufw"
firewall_remove_ufw_rules >/dev/null 2>&1
check '! grep -v "SSH (AdminPanelAZ)" "$RULES" | grep -q AdminPanelAZ' "правила панели удалены"
check 'has_rule "allow 22/tcp"' "правило SSH осталось"

echo "[test] ufw активен: правила пользователя не трогаются"
reset active
ufw allow 22/tcp
ufw allow 8443/tcp comment "my site"
install_rules
firewall_remove_ufw_rules >/dev/null 2>&1
check 'has_rule "allow 22/tcp" && has_rule "allow 8443/tcp"' "правила пользователя на месте"
check '! grep -q AdminPanelAZ "$RULES"' "правила панели удалены"
check '[[ "$(wc -l <"$RULES")" == 4 ]]' "удалены только правила панели"

echo "[test] больше 9 правил: номера вида [ 1] не мешают удалению"
reset active
for p in 5001 5002 5003 5004 5005; do ufw allow "$p/tcp"; done
install_rules
firewall_remove_ufw_rules >/dev/null 2>&1
check '! grep -q AdminPanelAZ "$RULES"' "правила панели удалены"

echo "[test] смена режима публикации на неактивном ufw: прежнее правило порта снимается"
reset inactive
firewall_ufw_close_port 8000 "AdminPanelAZ backend"
firewall_ufw_open_port 8000 "AdminPanelAZ backend (direct)"
check '! has_rule "deny 8000/tcp" && has_rule "allow 8000/tcp"' "DENY снят, ALLOW добавлен"
firewall_ufw_close_port 8000 "AdminPanelAZ backend"
check 'has_rule "deny 8000/tcp" && ! has_rule "allow 8000/tcp"' "обратно: ALLOW снят, DENY добавлен"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
