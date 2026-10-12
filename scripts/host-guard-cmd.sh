#!/usr/bin/env bash
# Охранная обёртка для run-shell-tests.sh: ставится в PATH под именами systemctl, nginx, iptables и т. п.
# Читающие вызовы передаёт настоящей команде, изменяющие (не подменённые самим тестом) блокирует и пишет в
# HOST_GUARD_LOG. iptables/ipset разрешены целиком только в отдельном network namespace (unshare --net).
set -uo pipefail

name="$(basename "$0")"
self="$(readlink -f "${BASH_SOURCE[0]}")"

# Настоящая команда — первая в PATH, которая не ведёт на эту же обёртку (охрана может быть вложенной).
real=""
IFS=: read -ra path_dirs <<<"${PATH:-}"
for dir in "${path_dirs[@]}"; do
  [[ -n "$dir" && -x "$dir/$name" ]] || continue
  [[ "$(readlink -f "$dir/$name")" == "$self" ]] && continue
  real="$dir/$name"
  break
done

isolated_netns() {
  local own init
  own="$(readlink /proc/self/ns/net 2>/dev/null)" || return 1
  init="$(readlink /proc/1/ns/net 2>/dev/null)" || return 1
  # Без root ссылка /proc/1/ns/net читается пустой — тогда изоляцию не доказать.
  [[ -n "$own" && -n "$init" && "$own" != "$init" ]]
}

argv=("$@")
has_arg() {
  local wanted arg
  for wanted in "$@"; do
    for arg in "${argv[@]}"; do
      [[ "$arg" == "$wanted" ]] && return 0
    done
  done
  return 1
}

args="$*"
allowed=false
case "$name" in
  systemctl)
    case "${1:-}" in
      is-active | is-enabled | is-failed | show | status | cat | list-units | list-unit-files | --version) allowed=true ;;
    esac
    ;;
  nginx)
    conf=""
    for ((i = 0; i < ${#argv[@]} - 1; i++)); do
      [[ "${argv[i]}" == "-c" ]] && conf="${argv[i + 1]}"
    done
    if [[ -z "$conf" || "$conf" == /etc/nginx/* ]]; then
      case "${1:-}" in
        -t | -T | -v | -V | -h) allowed=true ;;
      esac
    else
      # Свой экземпляр на временном конфиге хост не трогает, только если все temp-каталоги свои: иначе nginx
      # от root (даже с -t) отдаёт /var/lib/nginx/* пользователю nobody, и проксирование у www-data ломается.
      allowed=true
      for kind in client_body proxy fastcgi uwsgi scgi; do
        grep -Eqs "(^|[[:space:];{])${kind}_temp_path[[:space:]]" "$conf" || allowed=false
      done
    fi
    ;;
  iptables | ip6tables)
    if isolated_netns; then
      allowed=true
    elif has_arg -S -L --list --list-rules -C --check \
      && ! has_arg -A -I -D -R -F -X -N -P -Z -E --append --insert --delete --replace --flush; then
      allowed=true
    fi
    ;;
  iptables-save | ip6tables-save) allowed=true ;;
  iptables-restore | ip6tables-restore)
    isolated_netns && allowed=true
    ;;
  ipset)
    if isolated_netns; then
      allowed=true
    else
      case "${1:-}" in
        list | -L | test | -T | --version | -v) allowed=true ;;
      esac
    fi
    ;;
  ufw)
    case "${1:-}" in
      status | --version | version) allowed=true ;;
    esac
    ;;
  certbot)
    case "${1:-}" in
      certificates | --version) allowed=true ;;
    esac
    ;;
esac

if [[ "$allowed" != "true" ]]; then
  echo "$name $args" >>"${HOST_GUARD_LOG:-/dev/null}"
  echo "host-guard: заблокирован вызов на хосте: $name $args" >&2
  exit 97
fi
[[ -n "$real" ]] || { echo "host-guard: $name не найден" >&2; exit 127; }
exec "$real" "$@"
