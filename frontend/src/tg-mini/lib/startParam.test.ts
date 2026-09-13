import { describe, expect, it } from 'vitest'
import { mapTelegramStartParam } from '@/tg-mini/lib/startParam'

describe('mapTelegramStartParam', () => {
  it('maps supported deep-link params to routes', () => {
    expect(mapTelegramStartParam('awg2')).toBe('/awg2')
    expect(mapTelegramStartParam('warper')).toBe('/warper')
    expect(mapTelegramStartParam('cidr')).toBe('/cidr')
    expect(mapTelegramStartParam('nodes')).toBe('/nodes')
    expect(mapTelegramStartParam('configs')).toBe('/configs')
    expect(mapTelegramStartParam('settings')).toBe('/settings')
    expect(mapTelegramStartParam('unlock-codes')).toBe('/unlock-codes')
  })

  it('returns null for unsupported or empty values', () => {
    expect(mapTelegramStartParam('unknown')).toBeNull()
    expect(mapTelegramStartParam('__proto__')).toBeNull()
    expect(mapTelegramStartParam('constructor')).toBeNull()
    expect(mapTelegramStartParam('')).toBeNull()
    expect(mapTelegramStartParam(undefined)).toBeNull()
  })
})
