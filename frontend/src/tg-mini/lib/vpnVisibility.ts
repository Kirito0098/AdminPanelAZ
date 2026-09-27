import type { VisibleVpnProfilesPolicy } from '@/types'
import type { ProtocolFilter } from '@/tg-mini/components/MiniListToolbar'

/** Match panel useVisibleTabs / can_create_vpn_type for Mini App catalog. */
export function isVpnTypeVisibleInPolicy(
  vpnType: string,
  policy: VisibleVpnProfilesPolicy | null | undefined,
  isAdmin: boolean,
): boolean {
  if (isAdmin || !policy) return true
  const protocols = policy.protocols ?? []
  if (vpnType === 'openvpn') {
    return protocols.includes('openvpn') && (policy.openvpn_groups?.length ?? 0) > 0
  }
  if (vpnType === 'wireguard') {
    return protocols.includes('wireguard') || protocols.includes('amneziawg')
  }
  if (vpnType === 'amneziawg2') {
    return protocols.includes('amneziawg2')
  }
  return false
}

export function protocolFiltersForPolicy(
  policy: VisibleVpnProfilesPolicy | null | undefined,
  isAdmin: boolean,
): ProtocolFilter[] {
  const options: ProtocolFilter[] = ['all']
  if (isVpnTypeVisibleInPolicy('openvpn', policy, isAdmin)) options.push('openvpn')
  if (isVpnTypeVisibleInPolicy('wireguard', policy, isAdmin)) options.push('wireguard')
  if (isVpnTypeVisibleInPolicy('amneziawg2', policy, isAdmin)) options.push('amneziawg2')
  return options
}
