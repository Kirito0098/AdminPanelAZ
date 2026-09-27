import { describe, expect, it } from 'vitest'
import type { VisibleVpnProfilesPolicy } from '@/types'
import {
  isVpnTypeVisibleInPolicy,
  protocolFiltersForPolicy,
} from '@/tg-mini/lib/vpnVisibility'

const openvpnOnly: VisibleVpnProfilesPolicy = {
  routes: ['az', 'vpn'],
  protocols: ['openvpn'],
  openvpn_groups: ['udp'],
}

describe('vpnVisibility', () => {
  it('hides wireguard and awg2 when policy is openvpn-only', () => {
    expect(isVpnTypeVisibleInPolicy('openvpn', openvpnOnly, false)).toBe(true)
    expect(isVpnTypeVisibleInPolicy('wireguard', openvpnOnly, false)).toBe(false)
    expect(isVpnTypeVisibleInPolicy('amneziawg2', openvpnOnly, false)).toBe(false)
  })

  it('admin bypasses policy', () => {
    expect(isVpnTypeVisibleInPolicy('wireguard', openvpnOnly, true)).toBe(true)
    expect(protocolFiltersForPolicy(openvpnOnly, true)).toEqual([
      'all',
      'openvpn',
      'wireguard',
      'amneziawg2',
    ])
  })

  it('builds protocol chips from policy', () => {
    expect(protocolFiltersForPolicy(openvpnOnly, false)).toEqual(['all', 'openvpn'])
  })
})
