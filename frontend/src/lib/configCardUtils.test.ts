import { describe, expect, it } from 'vitest'
import { isAzProfile, isVpnProfile, profileProtocolForTab } from './configCardUtils'

describe('configCardUtils', () => {
  it('detects antizapret profile paths', () => {
    expect(isAzProfile({ path: '/root/antizapret/client/openvpn/antizapret/client.ovpn', variant: 'vpn' })).toBe(true)
    expect(isVpnProfile({ path: '/root/antizapret/client/openvpn/antizapret/client.ovpn', variant: 'vpn' })).toBe(false)
  })

  it('maps protocol tabs', () => {
    expect(profileProtocolForTab('openvpn')).toBe('openvpn')
    expect(profileProtocolForTab('amneziawg')).toBe('amneziawg')
    expect(profileProtocolForTab('wireguard')).toBe('wireguard')
  })
})
