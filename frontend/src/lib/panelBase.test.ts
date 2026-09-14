import { describe, expect, it } from 'vitest'
import { apiBaseForAccessPath, resolveAccessPath } from '@/lib/panelBase'

describe('resolveAccessPath', () => {
  it('derives ACCESS_PATH from Mini App pathname when inject is missing', () => {
    expect(
      resolveAccessPath({
        pathname: '/panel/api/tg-mini',
        injected: undefined,
        viteEnv: undefined,
      }),
    ).toBe('/panel')
    expect(apiBaseForAccessPath('/panel')).toBe('/panel/api')
  })

  it('keeps root Mini App on /api when ACCESS_PATH is empty', () => {
    expect(
      resolveAccessPath({
        pathname: '/api/tg-mini',
        injected: undefined,
        viteEnv: undefined,
      }),
    ).toBe('')
    expect(apiBaseForAccessPath('')).toBe('/api')
  })

  it('prefers injected __PANEL_ACCESS_PATH__ over pathname', () => {
    expect(
      resolveAccessPath({
        pathname: '/api/tg-mini',
        injected: '/panel',
        viteEnv: undefined,
      }),
    ).toBe('/panel')
  })

  it('forces empty path on bare portal /p even when inject is set', () => {
    expect(
      resolveAccessPath({
        pathname: '/p',
        injected: '/panel',
        viteEnv: undefined,
      }),
    ).toBe('')
  })

  it('forces empty path on portal /p/token even when inject is set', () => {
    expect(
      resolveAccessPath({
        pathname: '/p/token',
        injected: '/panel',
        viteEnv: undefined,
      }),
    ).toBe('')
  })

  it('derives ACCESS_PATH from deeper Mini App asset-like paths', () => {
    expect(
      resolveAccessPath({
        pathname: '/panel/api/tg-mini/assets/tg-mini-x.js',
        injected: undefined,
        viteEnv: undefined,
      }),
    ).toBe('/panel')
  })

  it('falls back to viteEnv when pathname is unrelated', () => {
    expect(
      resolveAccessPath({
        pathname: '/login',
        injected: undefined,
        viteEnv: '/panel',
      }),
    ).toBe('/panel')
  })
})
