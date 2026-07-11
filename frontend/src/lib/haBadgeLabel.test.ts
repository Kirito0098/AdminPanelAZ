import { describe, expect, it } from 'vitest'
import { formatHaBadgeLabel, formatHaNodeCount } from '@/lib/haBadgeLabel'

describe('formatHaNodeCount', () => {
  it('uses correct Russian plural forms', () => {
    expect(formatHaNodeCount(1)).toBe('1 узел')
    expect(formatHaNodeCount(2)).toBe('2 узла')
    expect(formatHaNodeCount(5)).toBe('5 узлов')
    expect(formatHaNodeCount(21)).toBe('21 узел')
  })
})

describe('formatHaBadgeLabel', () => {
  it('includes domain and explicit node count label', () => {
    expect(formatHaBadgeLabel({ shared_domain: 'vpn.example.com', node_count: 2 })).toBe(
      'HA: vpn.example.com · 2 узла',
    )
  })
})
