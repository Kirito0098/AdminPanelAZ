export function vpnTypeLabel(vpnType: string): string {
  if (vpnType === 'openvpn') return 'OpenVPN'
  if (vpnType === 'wireguard') return 'WireGuard'
  return vpnType
}

export function vpnTypeBadgeClass(vpnType: string): string {
  if (vpnType === 'openvpn') return 'tg-mini-protocol-ovpn'
  if (vpnType === 'wireguard') return 'tg-mini-protocol-wg'
  return 'tg-mini-protocol-default'
}
