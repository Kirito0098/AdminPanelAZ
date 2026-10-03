import { describe, expect, it } from 'vitest'
import { formatBytes } from '@/lib/trafficFormat'
import { formatBytes as warperFormatBytes } from '@/components/warper/utils'

describe('formatBytes', () => {
  it('formats sizes by unit', () => {
    expect(formatBytes(512)).toBe('512\u00A0B')
    expect(formatBytes(1536)).toBe('1.5\u00A0KB')
    expect(formatBytes(1.5 * 1024 ** 3)).toBe('1.50\u00A0GB')
  })

  it('returns a dash for invalid values', () => {
    expect(formatBytes(Number.NaN)).toBe('—')
    expect(formatBytes(-1)).toBe('—')
    expect(formatBytes(Number.POSITIVE_INFINITY)).toBe('—')
  })

  it('is the same function in Warper utils', () => {
    expect(warperFormatBytes).toBe(formatBytes)
  })
})
