import { describe, expect, it } from 'vitest'
import { applyGroupToggle, enabledCount, isIndeterminate, shouldShowGroupToggle } from './notifyGroups'

describe('enabledCount', () => {
  it('counts enabled keys from toggles', () => {
    expect(enabledCount(['a', 'b', 'c'], { a: true, b: false, c: true })).toBe(2)
  })

  it('treats missing keys as disabled', () => {
    expect(enabledCount(['a', 'b'], { a: true })).toBe(1)
  })

  it('returns 0 for an empty group', () => {
    expect(enabledCount([], { a: true })).toBe(0)
  })
})

describe('isIndeterminate', () => {
  it('is true when only some keys are enabled', () => {
    expect(isIndeterminate(['a', 'b'], { a: true, b: false })).toBe(true)
  })

  it('is false when all keys are enabled', () => {
    expect(isIndeterminate(['a', 'b'], { a: true, b: true })).toBe(false)
  })

  it('is false when all keys are disabled', () => {
    expect(isIndeterminate(['a', 'b'], { a: false, b: false })).toBe(false)
  })

  it('is false for an empty group', () => {
    expect(isIndeterminate([], {})).toBe(false)
  })
})

describe('applyGroupToggle', () => {
  it('writes true to every key of the group', () => {
    expect(applyGroupToggle({ a: false, b: false, other: true }, ['a', 'b'], true)).toEqual({
      a: true,
      b: true,
      other: true,
    })
  })

  it('writes false to every key of the group', () => {
    expect(applyGroupToggle({ a: true, b: true, other: true }, ['a', 'b'], false)).toEqual({
      a: false,
      b: false,
      other: true,
    })
  })

  it('does not mutate the input toggles', () => {
    const prev = { a: false }
    applyGroupToggle(prev, ['a'], true)
    expect(prev).toEqual({ a: false })
  })
})

describe('shouldShowGroupToggle', () => {
  it('hides the group toggle when a single group is present', () => {
    expect(shouldShowGroupToggle(1)).toBe(false)
  })

  it('shows group toggles for multiple groups', () => {
    expect(shouldShowGroupToggle(9)).toBe(true)
  })

  it('hides the group toggle when there are no groups', () => {
    expect(shouldShowGroupToggle(0)).toBe(false)
  })
})
