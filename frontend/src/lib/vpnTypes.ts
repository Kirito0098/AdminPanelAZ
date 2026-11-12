const VPN_TYPE_LABELS: Record<string, string> = {
  wireguard: 'WireGuard',
  openvpn: 'OpenVPN',
  amneziawg: 'AmneziaWG',
  amneziawg2: 'AmneziaWG 2.0',
}

/** Компактная подпись для бейджей и легенд графиков. */
const VPN_TYPE_SHORT_LABELS: Record<string, string> = {
  amneziawg2: 'AWG 2.0',
}

/** Подпись типа VPN для UI: openvpn → OpenVPN, неизвестное — как есть. */
export function vpnTypeLabel(type: string): string {
  return VPN_TYPE_LABELS[type] ?? type
}

/** Короткая подпись протокола: amneziawg2 → AWG 2.0, остальные — как в vpnTypeLabel. */
export function protocolLabel(protocol: string): string {
  return VPN_TYPE_SHORT_LABELS[protocol] ?? vpnTypeLabel(protocol)
}

/** Вариант бейджа протокола: OpenVPN — primary, WireGuard — secondary, остальные — outline. */
export function protocolBadgeVariant(protocol: string): 'default' | 'secondary' | 'outline' {
  const value = (protocol || '').toLowerCase()
  if (value === 'openvpn') return 'default'
  if (value === 'wireguard') return 'secondary'
  return 'outline'
}
