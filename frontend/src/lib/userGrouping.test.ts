import { describe, expect, it } from 'vitest'
import type { TrafficClientRow } from '@/types'
import {
  UNOWNED_USER_KEY,
  groupTrafficRowsByUser,
  userGroupKey,
  userGroupLabel,
} from './userGrouping'

function row(overrides: Partial<TrafficClientRow>): TrafficClientRow {
  return {
    common_name: 'client',
    protocol_type: 'openvpn',
    total_received: 0,
    total_sent: 0,
    total_bytes: 0,
    total_received_vpn: 0,
    total_sent_vpn: 0,
    total_bytes_vpn: 0,
    total_received_antizapret: 0,
    total_sent_antizapret: 0,
    total_bytes_antizapret: 0,
    traffic_period: 0,
    total_sessions: 0,
    is_active: false,
    ...overrides,
  }
}

describe('userGroupKey / userGroupLabel', () => {
  it('keys known owners by id and everything else as unowned', () => {
    expect(userGroupKey(7)).toBe('user:7')
    expect(userGroupKey(null)).toBe(UNOWNED_USER_KEY)
    expect(userGroupKey(undefined)).toBe(UNOWNED_USER_KEY)
  })

  it('falls back to a readable label', () => {
    expect(userGroupLabel('alice')).toBe('alice')
    expect(userGroupLabel('  ')).toBe('Без владельца')
    expect(userGroupLabel(null)).toBe('Без владельца')
  })
})

describe('groupTrafficRowsByUser', () => {
  it('sums traffic and counts configs per owner', () => {
    const groups = groupTrafficRowsByUser([
      row({
        common_name: 'alice-1',
        protocol_type: 'openvpn',
        owner_id: 1,
        owner_username: 'alice',
        total_received: 100,
        total_sent: 50,
        total_bytes: 150,
        traffic_period: 30,
        is_active: true,
        last_seen_at: '2026-10-21T10:00:00',
      }),
      row({
        common_name: 'alice-2',
        protocol_type: 'wireguard',
        owner_id: 1,
        owner_username: 'alice',
        total_received: 10,
        total_sent: 5,
        total_bytes: 15,
        traffic_period: 7,
        last_seen_at: '2026-10-21T12:00:00',
      }),
    ])

    expect(groups).toHaveLength(1)
    expect(groups[0]).toMatchObject({
      key: 'user:1',
      username: 'alice',
      configsCount: 2,
      activeConfigsCount: 1,
      totalReceived: 110,
      totalSent: 55,
      totalBytes: 165,
      trafficPeriod: 37,
      isActive: true,
      lastSeenAt: '2026-10-21T12:00:00',
    })
    expect(groups[0].protocols).toEqual(['openvpn', 'wireguard'])
  })

  it('puts clients without a config into one unowned group', () => {
    const groups = groupTrafficRowsByUser([
      row({ common_name: 'legacy-1', total_bytes: 10 }),
      row({ common_name: 'legacy-2', total_bytes: 20 }),
    ])

    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe(UNOWNED_USER_KEY)
    expect(groups[0].username).toBe('Без владельца')
    expect(groups[0].configsCount).toBe(2)
    expect(groups[0].totalBytes).toBe(30)
  })

  it('orders users by total traffic', () => {
    const groups = groupTrafficRowsByUser([
      row({ owner_id: 1, owner_username: 'small', total_bytes: 1 }),
      row({ owner_id: 2, owner_username: 'big', total_bytes: 100 }),
    ])

    expect(groups.map((group) => group.username)).toEqual(['big', 'small'])
  })
})
