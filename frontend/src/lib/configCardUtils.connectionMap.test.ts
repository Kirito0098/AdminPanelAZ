import { describe, expect, it } from 'vitest'
import {
  buildClientConnectionMap,
  isConfigConnected,
  openvpnTransportFromClient,
} from './configCardUtils'
import type { OpenVpnClient, WireGuardPeer } from '@/types'

function ovpn(partial: Partial<OpenVpnClient> & Pick<OpenVpnClient, 'common_name'>): OpenVpnClient {
  return {
    common_name: partial.common_name,
    real_address: partial.real_address ?? '',
    virtual_address: partial.virtual_address ?? '',
    connected_since: partial.connected_since ?? '',
    bytes_received: partial.bytes_received ?? 0,
    bytes_sent: partial.bytes_sent ?? 0,
    profile: partial.profile,
  }
}

function peer(partial: Partial<WireGuardPeer> & Pick<WireGuardPeer, 'client_name'>): WireGuardPeer {
  return {
    interface: partial.interface ?? 'awg0',
    public_key: partial.public_key ?? 'pk',
    endpoint: partial.endpoint ?? null,
    allowed_ips: partial.allowed_ips ?? '10.0.0.2/32',
    latest_handshake: partial.latest_handshake ?? null,
    transfer_rx: partial.transfer_rx ?? 0,
    transfer_tx: partial.transfer_tx ?? 0,
    client_name: partial.client_name,
  }
}

describe('buildClientConnectionMap', () => {
  it('marks each protocol from its own federated list', () => {
    // Naive UTC within 180s window (backend style without Z).
    const fresh = new Date(Date.now() - 30_000).toISOString().replace(/Z$/, '')

    const map = buildClientConnectionMap(
      [ovpn({ common_name: 'ovpn-user', profile: 'antizapret-udp' })],
      [peer({ client_name: 'wg-or-awg', latest_handshake: fresh })],
      [peer({ client_name: 'awg2-user', latest_handshake: fresh })],
    )

    expect(isConfigConnected('ovpn-user', 'openvpn', map)).toBe(true)
    expect(isConfigConnected('wg-or-awg', 'wireguard', map)).toBe(true)
    expect(isConfigConnected('wg-or-awg', 'amneziawg', map)).toBe(true)
    expect(isConfigConnected('awg2-user', 'amneziawg2', map)).toBe(true)
    expect(isConfigConnected('awg2-user', 'wireguard', map)).toBe(false)
    expect(isConfigConnected('wg-or-awg', 'amneziawg2', map)).toBe(false)
    expect(isConfigConnected('ovpn-user', 'wireguard', map)).toBe(false)
  })

  it('keeps OpenVPN online when profile has -udp', () => {
    const map = buildClientConnectionMap(
      [ovpn({ common_name: 'Alice', profile: 'antizapret-udp', real_address: 'udp4:1.2.3.4:1' })],
      [],
    )
    expect(isConfigConnected('Alice', 'openvpn', map, 'GROUP_UDP')).toBe(true)
    expect(isConfigConnected('Alice', 'openvpn', map, 'GROUP_TCP')).toBe(false)
  })

  it('counts OpenVPN online for GROUP_UDP when transport is unknown', () => {
    const map = buildClientConnectionMap(
      [ovpn({ common_name: 'Keenetic_X', profile: 'antizapret', real_address: '1.2.3.4:1194' })],
      [],
    )
    expect(isConfigConnected('Keenetic_X', 'openvpn', map, 'GROUP_UDP')).toBe(true)
    expect(isConfigConnected('Keenetic_X', 'openvpn', map, 'GROUP_TCP')).toBe(true)
  })

  it('marks federated HA peer online on OpenVPN tab', () => {
    const map = buildClientConnectionMap(
      [ovpn({ common_name: 'Keenetic_Bogachevs', profile: 'antizapret-udp' })],
      [],
      [],
    )
    expect(isConfigConnected('Keenetic_Bogachevs', 'openvpn', map, 'GROUP_UDP\\TCP')).toBe(true)
  })
})

describe('openvpnTransportFromClient', () => {
  it('falls back to real_address prefix when profile has no -udp/-tcp', () => {
    expect(openvpnTransportFromClient(ovpn({ common_name: 'x', profile: 'antizapret', real_address: 'udp4:1.1.1.1:9' }))).toBe(
      'udp',
    )
    expect(openvpnTransportFromClient(ovpn({ common_name: 'x', profile: 'vpn', real_address: 'tcp4:1.1.1.1:9' }))).toBe(
      'tcp',
    )
  })
})
