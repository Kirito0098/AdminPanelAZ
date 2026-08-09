import { describe, expect, it } from 'vitest'
import { buildLightDiff, countDiffOps } from './buildLightDiff'

describe('buildLightDiff', () => {
  it('shows added domain when file was only a trailing newline', () => {
    const result = buildLightDiff('\n', 'lazyweb.com\n')
    expect(result.ops.some((op) => op.type === 'add' && op.text === 'lazyweb.com')).toBe(true)
    expect(result.ops.every((op) => op.lineNumber > 0)).toBe(true)
    expect(countDiffOps(result.ops)).toEqual({ added: 1, removed: 1 })
  })

  it('adds a domain to an empty file', () => {
    expect(buildLightDiff('', 'lazyweb.com').ops).toEqual([
      { type: 'add', lineNumber: 1, text: 'lazyweb.com' },
    ])
  })

  it('appends a domain after an existing line', () => {
    expect(buildLightDiff('foo\n', 'foo\nlazyweb.com\n').ops).toEqual([
      { type: 'add', lineNumber: 2, text: 'lazyweb.com' },
    ])
  })

  it('appends without trailing newline on either side', () => {
    expect(buildLightDiff('foo', 'foo\nlazyweb.com').ops).toEqual([
      { type: 'add', lineNumber: 2, text: 'lazyweb.com' },
    ])
  })

  it('replaces a line', () => {
    expect(buildLightDiff('a\nb\n', 'a\nc\n').ops).toEqual([
      { type: 'remove', lineNumber: 2, text: 'b' },
      { type: 'add', lineNumber: 2, text: 'c' },
    ])
  })

  it('inserts a line in the middle', () => {
    expect(buildLightDiff('x\ny\n', 'x\nz\ny\n').ops).toEqual([
      { type: 'add', lineNumber: 2, text: 'z' },
    ])
  })

  it('never emits L0 / empty lineNumber ops', () => {
    const cases: Array<[string, string]> = [
      ['\n', 'lazyweb.com'],
      ['\n', 'lazyweb.com\n'],
      ['\n\n', 'lazyweb.com\n'],
      ['a\nb', 'c\nd'],
      ['', 'a\nb'],
    ]
    for (const [base, current] of cases) {
      for (const op of buildLightDiff(base, current).ops) {
        expect(op.lineNumber).toBeGreaterThan(0)
        expect(op.text).toBeTypeOf('string')
      }
    }
  })
})
