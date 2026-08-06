import { describe, expect, it } from 'vitest'

import type { OpenVpnClient, WireGuardPeer } from '@/types'

import {
  buildClientConnectionMap,
  isConfigConnected,
  openvpnTransportFromProfile,
  resolveDisplayedTraffic,
} from './configCardUtils'

function ovpn(partial: Partial<OpenVpnClient> & Pick<OpenVpnClient, 'common_name'>): OpenVpnClient {
  return {
    real_address: '1.2.3.4:1194',
    virtual_address: '10.0.0.2',
    bytes_received: 0,
    bytes_sent: 0,
    connected_since: '',
    ...partial,
  }
}

describe('openvpnTransportFromProfile', () => {
  it('detects udp and tcp suffixes', () => {
    expect(openvpnTransportFromProfile('antizapret-udp')).toBe('udp')
    expect(openvpnTransportFromProfile('vpn-tcp')).toBe('tcp')
    expect(openvpnTransportFromProfile('antizapret')).toBeNull()
    expect(openvpnTransportFromProfile(null)).toBeNull()
  })
})

describe('buildClientConnectionMap / isConfigConnected', () => {
  it('tracks OpenVPN UDP and TCP separately', () => {
    const map = buildClientConnectionMap(
      [
        ovpn({ common_name: 'Alice', profile: 'vpn-udp' }),
        ovpn({ common_name: 'Bob', profile: 'antizapret-tcp' }),
        ovpn({ common_name: 'Carol', profile: 'vpn-udp' }),
        ovpn({ common_name: 'Carol', profile: 'vpn-tcp' }),
      ],
      [],
    )

    expect(isConfigConnected('Alice', 'openvpn', map, 'GROUP_UDP')).toBe(true)
    expect(isConfigConnected('Alice', 'openvpn', map, 'GROUP_TCP')).toBe(false)
    expect(isConfigConnected('Alice', 'openvpn', map, 'GROUP_UDP\\TCP')).toBe(true)

    expect(isConfigConnected('Bob', 'openvpn', map, 'GROUP_UDP')).toBe(false)
    expect(isConfigConnected('Bob', 'openvpn', map, 'GROUP_TCP')).toBe(true)

    expect(isConfigConnected('Carol', 'openvpn', map, 'GROUP_UDP')).toBe(true)
    expect(isConfigConnected('Carol', 'openvpn', map, 'GROUP_TCP')).toBe(true)
  })

  it('keeps wireguard independent of OpenVPN group', () => {
    const peers: WireGuardPeer[] = [
      {
        client_name: 'Alice',
        interface: 'vpn',
        public_key: 'x',
        endpoint: '1.1.1.1:51820',
        allowed_ips: '10.8.0.2/32',
        latest_handshake: new Date().toISOString(),
        transfer_rx: 1,
        transfer_tx: 1,
      },
    ]
    const map = buildClientConnectionMap([], peers)
    expect(isConfigConnected('Alice', 'wireguard', map, 'GROUP_UDP')).toBe(true)
    expect(isConfigConnected('Alice', 'openvpn', map, 'GROUP_UDP')).toBe(false)
  })

  it('captures issued local IPs from OpenVPN and WireGuard', () => {
    const map = buildClientConnectionMap(
      [ovpn({ common_name: 'Alice', virtual_address: '10.0.0.2' })],
      [
        {
          client_name: 'Bob',
          interface: 'vpn',
          public_key: 'y',
          endpoint: null,
          allowed_ips: '10.8.0.5/32',
          latest_handshake: null,
          transfer_rx: 0,
          transfer_tx: 0,
        },
      ],
    )
    expect(map.alice?.localIp).toBe('10.0.0.2')
    expect(map.bob?.localIp).toBe('10.8.0.5')
  })
})

describe('resolveDisplayedTraffic', () => {
  it('picks udp/tcp consumed fields from the group toggle', () => {
    const policy = {
      is_blocked: false,
      block_mode: 'none',
      traffic_consumed_bytes: 1000,
      traffic_consumed_human: '1 KB',
      traffic_consumed_udp_bytes: 100,
      traffic_consumed_udp_human: '100 B',
      traffic_consumed_tcp_bytes: 200,
      traffic_consumed_tcp_human: '200 B',
    }

    expect(resolveDisplayedTraffic(policy, 'GROUP_UDP')).toEqual({ bytes: 100, human: '100 B' })
    expect(resolveDisplayedTraffic(policy, 'GROUP_TCP')).toEqual({ bytes: 200, human: '200 B' })
    expect(resolveDisplayedTraffic(policy, 'GROUP_UDP\\TCP')).toEqual({ bytes: 1000, human: '1 KB' })
  })
})
