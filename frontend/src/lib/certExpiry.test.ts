import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { certDaysLeft, formatCertExpiry, parseCertExpiresAt } from '@/lib/configCardUtils'
import type { VpnConfig } from '@/types'

function makeConfig(overrides: Partial<VpnConfig>): VpnConfig {
  return {
    id: 1,
    client_name: 'alice',
    vpn_type: 'openvpn',
    owner_id: 1,
    created_at: '2024-01-01T00:00:00',
    updated_at: '2024-01-01T00:00:00',
    profile_files: [],
    ...overrides,
  } as VpnConfig
}

describe('parseCertExpiresAt', () => {
  it('reads timestamps without a zone suffix as UTC', () => {
    expect(parseCertExpiresAt('2035-05-12T10:00:00')?.toISOString()).toBe('2035-05-12T10:00:00.000Z')
  })

  it('respects an explicit zone when present', () => {
    expect(parseCertExpiresAt('2035-05-12T13:00:00+03:00')?.toISOString()).toBe(
      '2035-05-12T10:00:00.000Z',
    )
  })

  it('returns null for empty or invalid input', () => {
    expect(parseCertExpiresAt(null)).toBeNull()
    expect(parseCertExpiresAt('')).toBeNull()
    expect(parseCertExpiresAt('nonsense')).toBeNull()
  })
})

describe('certDaysLeft', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('counts down from the real expiry date, ignoring the issued term', () => {
    const config = makeConfig({ cert_expire_days: 3650, cert_expires_at: '2026-03-02T00:00:00' })
    expect(certDaysLeft(config)).toBe(60)
  })

  it('reports zero for an expired certificate', () => {
    const config = makeConfig({ cert_expire_days: 3650, cert_expires_at: '2025-12-01T00:00:00' })
    expect(certDaysLeft(config)).toBe(0)
  })

  it('is unknown while the node has not been read yet', () => {
    expect(certDaysLeft(makeConfig({ cert_expire_days: 3650 }))).toBeNull()
  })
})

describe('formatCertExpiry', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows days left together with the expiry date', () => {
    const text = formatCertExpiry(
      makeConfig({ cert_expire_days: 3650, cert_expires_at: '2026-03-02T12:00:00' }),
    )
    expect(text).toContain('60 дн.')
    expect(text).toContain('2026')
  })

  it('marks an expired certificate instead of showing days', () => {
    const text = formatCertExpiry(
      makeConfig({ cert_expire_days: 3650, cert_expires_at: '2025-12-01T00:00:00' }),
    )
    expect(text).toContain('истёк')
    expect(text).not.toContain('3650')
  })

  it('falls back to the issued term with explicit wording when expiry is unknown', () => {
    expect(formatCertExpiry(makeConfig({ cert_expire_days: 3650 }))).toBe('выпущен на 3650 дн.')
  })
})
