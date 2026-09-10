import { describe, expect, it } from 'vitest'
import { setActiveTimeZone } from '@/lib/datetime'
import {
  availableDateBounds,
  calendarDateInZone,
  formatLocalDate,
  isAppliedCustomValid,
  isTrafficPeriodHttpError,
  overviewPeriodSubtitle,
  parseLocalDate,
  validateCustomRange,
} from './trafficPeriod'

describe('trafficPeriod', () => {
  // Midday UTC so panel-zone "today" is stable as 2026-09-10 for UTC.
  const now = new Date('2026-09-10T12:00:00.000Z')

  it('bounds last N days inclusive in UTC panel zone', () => {
    setActiveTimeZone('UTC')
    const { min, max } = availableDateBounds(90, now, 'UTC')
    // max is a local Date bag whose Y/M/D match panel "today"
    expect(formatLocalDate(max)).toBe('2026-09-10')
    expect(calendarDateInZone(now, 'UTC')).toBe('2026-09-10')
    const diff = Math.round((max.getTime() - min.getTime()) / 86400000)
    expect(diff).toBe(90)
  })

  it('rejects range older than retention with retention message', () => {
    setActiveTimeZone('UTC')
    const from = parseLocalDate('2026-01-01')!
    const to = parseLocalDate('2026-09-10')!
    const err = validateCustomRange(from, to, 90, now, 'UTC')
    expect(err).toMatch(/90/)
    expect(err).toMatch(/хранятся/)
  })

  it('distinct messages for order and future', () => {
    setActiveTimeZone('UTC')
    expect(
      validateCustomRange(parseLocalDate('2026-09-08')!, parseLocalDate('2026-09-01')!, 90, now, 'UTC'),
    ).toMatch(/позже/)
    expect(
      validateCustomRange(parseLocalDate('2026-09-11')!, parseLocalDate('2026-09-12')!, 90, now, 'UTC'),
    ).toMatch(/будущ/)
  })

  it('isAppliedCustomValid rejects out-of-retention ISO range', () => {
    setActiveTimeZone('UTC')
    expect(isAppliedCustomValid('2026-01-01', '2026-09-10', 30, now, 'UTC')).toBe(false)
    expect(isAppliedCustomValid('2026-09-01', '2026-09-10', 30, now, 'UTC')).toBe(true)
    expect(isAppliedCustomValid('bad', '2026-09-10', 30, now, 'UTC')).toBe(false)
  })

  it('overviewPeriodSubtitle shows preset, applied custom, or not applied', () => {
    expect(overviewPeriodSubtitle('preset', '30d', '', '')).toBe('30д')
    expect(overviewPeriodSubtitle('preset', '7d', '2026-01-01', '2026-01-02')).toBe('7д')
    expect(overviewPeriodSubtitle('custom', '30d', '2026-09-01', '2026-09-10')).toBe(
      '2026-09-01 — 2026-09-10',
    )
    expect(overviewPeriodSubtitle('custom', '30d', '', '')).toBe('не применено')
  })

  it('isTrafficPeriodHttpError detects period 400s', () => {
    expect(isTrafficPeriodHttpError({ status: 400, message: 'Данные трафика хранятся только 90 дн.' })).toBe(
      true,
    )
    expect(isTrafficPeriodHttpError({ status: 400, message: 'Дата «от» не может быть позже даты «до».' })).toBe(
      true,
    )
    expect(isTrafficPeriodHttpError({ status: 500, message: 'хранятся' })).toBe(false)
    expect(isTrafficPeriodHttpError({ status: 400, message: 'Недостаточно прав' })).toBe(false)
  })
})
