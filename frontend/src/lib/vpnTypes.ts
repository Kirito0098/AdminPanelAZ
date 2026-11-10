const VPN_TYPE_LABELS: Record<string, string> = {
  wireguard: 'WireGuard',
  openvpn: 'OpenVPN',
  amneziawg2: 'AmneziaWG 2.0',
}

/** Подпись типа VPN для UI: openvpn → OpenVPN, неизвестное — как есть. */
export function vpnTypeLabel(type: string): string {
  return VPN_TYPE_LABELS[type] ?? type
}
