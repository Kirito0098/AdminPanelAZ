import { describe, expect, it } from 'vitest'
import {
  effectiveHaWireguardDomain,
  formatHaBadgeLabel,
  formatHaNodeCount,
  formatHaSharedDomains,
} from '@/lib/haBadgeLabel'

describe('formatHaNodeCount', () => {
  it('uses correct Russian plural forms', () => {
    expect(formatHaNodeCount(1)).toBe('1 узел')
    expect(formatHaNodeCount(2)).toBe('2 узла')
    expect(formatHaNodeCount(5)).toBe('5 узлов')
    expect(formatHaNodeCount(21)).toBe('21 узел')
  })
})

describe('formatHaBadgeLabel', () => {
  it('includes domain and explicit node count label', () => {
    expect(formatHaBadgeLabel({ shared_domain: 'vpn.example.com', node_count: 2 })).toBe(
      'HA: vpn.example.com · 2 узла',
    )
  })
})

describe('formatHaSharedDomains', () => {
  it('returns one domain when openvpn and wireguard match', () => {
    expect(
      formatHaSharedDomains({
        shared_domain: 'vpn.example.com',
        shared_domain_wireguard: 'vpn.example.com',
      }),
    ).toBe('vpn.example.com')
  })

  it('falls back wireguard to openvpn when empty', () => {
    expect(effectiveHaWireguardDomain({ shared_domain: 'vpn.example.com' })).toBe('vpn.example.com')
    expect(formatHaSharedDomains({ shared_domain: 'vpn.example.com' })).toBe('vpn.example.com')
  })

  it('shows both when domains differ', () => {
    expect(
      formatHaSharedDomains({
        shared_domain: 'ovpn.example.com',
        shared_domain_wireguard: 'awg.example.com',
      }),
    ).toBe('ovpn.example.com / awg.example.com')
  })
})
