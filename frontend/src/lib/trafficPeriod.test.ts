import { describe, expect, it } from 'vitest'
import {
  availableDateBounds,
  isAppliedCustomValid,
  overviewPeriodSubtitle,
  validateCustomRange,
} from './trafficPeriod'

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

  it('isAppliedCustomValid rejects out-of-retention ISO range', () => {
    expect(isAppliedCustomValid('2026-01-01', '2026-09-10', 30, today)).toBe(false)
    expect(isAppliedCustomValid('2026-09-01', '2026-09-10', 30, today)).toBe(true)
    expect(isAppliedCustomValid('bad', '2026-09-10', 30, today)).toBe(false)
  })

  it('overviewPeriodSubtitle shows preset or applied custom', () => {
    expect(overviewPeriodSubtitle('preset', '30d', '', '')).toBe('30д')
    expect(overviewPeriodSubtitle('preset', '7d', '2026-01-01', '2026-01-02')).toBe('7д')
    expect(overviewPeriodSubtitle('custom', '30d', '2026-09-01', '2026-09-10')).toBe(
      '2026-09-01 — 2026-09-10',
    )
  })
})
