import { PROTOCOL_ORDER, protocolKey, type Protocol } from '@/lib/vpnTypes'
import type { VisibleVpnProfilesPolicy } from '@/types'
import type { ProtocolFilter } from '@/tg-mini/components/MiniListToolbar'

/**
 * Категория фильтра для сырого vpn_type: AmneziaWG 1.5 входит в WG/AWG 1.5,
 * неизвестное значение — null (в счётчики не попадает).
 */
export function protocolFilterForVpnType(vpnType: string): ProtocolFilter | null {
  const key = protocolKey(vpnType)
  if (key === 'amneziawg') return 'wireguard'
  return key === 'openvpn' || key === 'wireguard' || key === 'amneziawg2' ? key : null
}

/**
 * Протоколы, включённые модулями в фичах (без учёта policy видимости).
 * Та же логика, что у CreateConfigDialog: OpenVPN/WireGuard по умолчанию включены.
 */
export function featureEnabledProtocols(
  features: Record<string, boolean> | null | undefined,
): Protocol[] {
  const flags = features ?? {}
  return PROTOCOL_ORDER.filter((protocol) => {
    if (protocol === 'openvpn') return Boolean(flags.openvpn ?? true)
    if (protocol === 'wireguard') return Boolean(flags.wireguard ?? true) || Boolean(flags.amneziawg)
    return Boolean(flags.awg2)
  })
}

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
  return [
    'all',
    ...PROTOCOL_ORDER.filter((protocol) => isVpnTypeVisibleInPolicy(protocol, policy, isAdmin)),
  ]
}
