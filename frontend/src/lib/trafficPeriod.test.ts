import { describe, expect, it } from 'vitest'
import { availableDateBounds, validateCustomRange } from './trafficPeriod'

describe('trafficPeriod', () => {
  const today = new Date(2026, 8, 10) // local Sep 10 2026

  it('bounds last N days inclusive', () => {
    const { min, max } = availableDateBounds(90, today)
    expect(max.toDateString()).toBe(today.toDateString())
    const diff = Math.round((max.getTime() - min.getTime()) / 86400000)
    expect(diff).toBe(90)
  })

  it('rejects range older than retention', () => {
    const err = validateCustomRange(new Date(2026, 0, 1), today, 90, today)
    expect(err).toMatch(/90/)
  })
})
