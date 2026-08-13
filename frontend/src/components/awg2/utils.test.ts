import { describe, expect, it } from 'vitest'
import {
  awg2StatusMeta,
  formatAwg2ClientCount,
  formatAwg2IfacePort,
} from './utils'
import type { Awg2HealthResponse, Awg2StatusResponse } from '@/types'

describe('awg2StatusMeta', () => {
  it('handles null / not installed / installed', () => {
    expect(awg2StatusMeta(null).label).toBe('Нет данных')
    expect(awg2StatusMeta({ installed: false } as Awg2HealthResponse).label).toBe('Не установлен')
    expect(awg2StatusMeta({ installed: true } as Awg2HealthResponse).variant).toBe('success')
  })
})

describe('formatAwg2ClientCount', () => {
  it('prefers vpn then antizapret then dash', () => {
    expect(formatAwg2ClientCount(null)).toBe('—')
    expect(formatAwg2ClientCount({ installed: true, client_counts: { vpn: 3 } } as Awg2StatusResponse)).toBe('3')
    expect(
      formatAwg2ClientCount({ installed: true, client_counts: { antizapret: 2 } } as Awg2StatusResponse),
    ).toBe('2')
  })
})

describe('formatAwg2IfacePort', () => {
  it('joins available parts', () => {
    expect(formatAwg2IfacePort('vpn-awg', '37891')).toBe('vpn-awg · 37891')
    expect(formatAwg2IfacePort('vpn-awg', null)).toBe('vpn-awg')
    expect(formatAwg2IfacePort(null, null)).toBe('—')
  })
})
