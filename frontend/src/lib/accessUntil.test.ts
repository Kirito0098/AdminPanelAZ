import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/http'
import { dateInputToIso, isoToDateInput, parseAccessUntilConflict } from './accessUntil'

const CONFLICT_PAYLOAD = {
  code: 'access_until_conflict',
  user_access_until: '2026-10-01T20:59:59.999000+00:00',
  client_access_until: '2026-11-01T20:59:59.999000+00:00',
}

describe('dateInputToIso', () => {
  it('maps a date input to the end of that local day', () => {
    const iso = dateInputToIso('2026-10-01')
    expect(iso).not.toBeNull()
    const parsed = new Date(iso as string)
    expect(parsed.getFullYear()).toBe(2026)
    expect(parsed.getMonth()).toBe(9)
    expect(parsed.getDate()).toBe(1)
    expect(parsed.getHours()).toBe(23)
    expect(parsed.getMinutes()).toBe(59)
    expect(parsed.getSeconds()).toBe(59)
  })

  it('returns null for empty and malformed values', () => {
    expect(dateInputToIso('')).toBeNull()
    expect(dateInputToIso('01.10.2026')).toBeNull()
  })

  it('round-trips through isoToDateInput', () => {
    expect(isoToDateInput(dateInputToIso('2026-10-01'))).toBe('2026-10-01')
  })
})

describe('isoToDateInput', () => {
  it('returns an empty string for missing values', () => {
    expect(isoToDateInput(null)).toBe('')
    expect(isoToDateInput(undefined)).toBe('')
    expect(isoToDateInput('nonsense')).toBe('')
  })
})

describe('parseAccessUntilConflict', () => {
  it('parses a 409 ApiError payload', () => {
    const conflict = parseAccessUntilConflict(
      new ApiError('conflict', 409, CONFLICT_PAYLOAD),
    )
    expect(conflict).toEqual(CONFLICT_PAYLOAD)
  })

  it('parses an already-extracted payload rethrown between layers', () => {
    expect(parseAccessUntilConflict(CONFLICT_PAYLOAD)).toEqual(CONFLICT_PAYLOAD)
  })

  it('normalizes missing deadlines to null', () => {
    const conflict = parseAccessUntilConflict(
      new ApiError('conflict', 409, { code: 'access_until_conflict' }),
    )
    expect(conflict).toEqual({
      code: 'access_until_conflict',
      user_access_until: null,
      client_access_until: null,
    })
  })

  it('ignores other statuses, codes and plain errors', () => {
    expect(parseAccessUntilConflict(new ApiError('boom', 400, CONFLICT_PAYLOAD))).toBeNull()
    expect(parseAccessUntilConflict(new ApiError('boom', 409, { code: 'other' }))).toBeNull()
    expect(parseAccessUntilConflict(new ApiError('boom', 409, 'text'))).toBeNull()
    expect(parseAccessUntilConflict(new Error('boom'))).toBeNull()
    expect(parseAccessUntilConflict(null)).toBeNull()
  })
})
