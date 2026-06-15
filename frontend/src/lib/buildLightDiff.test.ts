import { describe, expect, it } from 'vitest'
import { countDiffOps, formatDiffSummary, type DiffOp } from './buildLightDiff'

describe('buildLightDiff helpers', () => {
  it('countDiffOps aggregates add/remove', () => {
    const ops: DiffOp[] = [
      { type: 'add', lineNumber: 1, text: 'x' },
      { type: 'remove', lineNumber: 2, text: 'y' },
      { type: 'remove', lineNumber: 3, text: 'z' },
    ]
    expect(countDiffOps(ops)).toEqual({ added: 1, removed: 2 })
  })

  it('formatDiffSummary handles empty diff', () => {
    expect(formatDiffSummary({ added: 0, removed: 0 })).toContain('Нет отличий')
  })

  it('formatDiffSummary summarizes changes', () => {
    expect(formatDiffSummary({ added: 2, removed: 1 })).toBe('Добавлено: 2, удалено: 1')
  })
})
