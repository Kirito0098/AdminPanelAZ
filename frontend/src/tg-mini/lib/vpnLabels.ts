export function vpnTypeLabel(vpnType: string): string {
  if (vpnType === 'openvpn') return 'OpenVPN'
  if (vpnType === 'wireguard') return 'WG/AWG 1.5'
  if (vpnType === 'amneziawg2') return 'AWG 2.0'
  return vpnType
}

export function vpnTypeBadgeClass(vpnType: string): string {
  if (vpnType === 'openvpn') return 'tg-mini-protocol-ovpn'
  if (vpnType === 'wireguard') return 'tg-mini-protocol-wg'
  if (vpnType === 'amneziawg2') return 'tg-mini-protocol-awg2'
  return 'tg-mini-protocol-default'
}
