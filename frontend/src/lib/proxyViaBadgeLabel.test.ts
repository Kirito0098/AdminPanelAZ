import { describe, expect, it } from 'vitest'
import { formatProxyViaBadgeLabel } from '@/lib/proxyViaBadgeLabel'

describe('formatProxyViaBadgeLabel', () => {
  it('resolved mapping shows short via-proxy mark', () => {
    expect(formatProxyViaBadgeLabel(true)).toBe('через прокси')
  })

  it('unresolved mapping mentions IP not restored', () => {
    expect(formatProxyViaBadgeLabel(false)).toBe('через прокси · IP не восстановлен')
    expect(formatProxyViaBadgeLabel(undefined)).toBe('через прокси · IP не восстановлен')
  })
})
