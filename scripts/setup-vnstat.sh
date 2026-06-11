#!/usr/bin/env bash
# Установка vnStat и регистрация VPN-интерфейсов для мониторинга трафика.
set -euo pipefail

log() { echo "[setup-vnstat] $*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Запустите от root: sudo $0"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
if ! command -v vnstat >/dev/null 2>&1; then
  log "Установка vnstat..."
  apt-get update -qq
  apt-get install -y vnstat
fi

systemctl enable vnstat >/dev/null 2>&1 || true
systemctl restart vnstat >/dev/null 2>&1 || true

declare -A seen=()
ifaces=()

add_iface() {
  local name="${1:-}"
  [[ -z "$name" ]] && return 0
  [[ -n "${seen[$name]:-}" ]] && return 0
  if ip link show "$name" >/dev/null 2>&1; then
    seen["$name"]=1
    ifaces+=("$name")
  fi
}

for fallback in vpn vpn-tcp vpn-udp antizapret antizapret-tcp antizapret-udp; do
  add_iface "$fallback"
done

if command -v wg >/dev/null 2>&1; then
  while read -r wg_iface; do
    add_iface "$wg_iface"
  done < <(wg show interfaces 2>/dev/null | tr ' ' '\n' | sed '/^$/d')
fi

if ((${#ifaces[@]} == 0)); then
  log "VPN-интерфейсы не найдены. Добавьте вручную: vnstat -u -i <iface>"
  exit 0
fi

for iface in "${ifaces[@]}"; do
  log "Регистрация интерфейса: $iface"
  vnstat -u -i "$iface" >/dev/null 2>&1 || vnstat --add -i "$iface" >/dev/null 2>&1 || true
done

systemctl restart vnstat >/dev/null 2>&1 || true
log "Готово. Интерфейсы: ${ifaces[*]}"
