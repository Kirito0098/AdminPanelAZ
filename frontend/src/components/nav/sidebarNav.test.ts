// frontend/src/components/nav/sidebarNav.test.ts
import { describe, expect, it } from 'vitest'
import {
  SIDEBAR_NAV_GROUPS,
  getVisibleSidebarNavGroups,
  isSidebarNavItemVisible,
} from './sidebarNav'

describe('SIDEBAR_NAV_GROUPS IA', () => {
  it('has four role groups in order', () => {
    expect(SIDEBAR_NAV_GROUPS.map((g) => g.label)).toEqual([
      'Клиенты',
      'Сеть',
      'Наблюдение',
      'Панель',
    ])
  })

  it('names home Клиенты at /', () => {
    const home = SIDEBAR_NAV_GROUPS[0].items[0]
    expect(home).toMatchObject({ to: '/', label: 'Клиенты', end: true })
  })

  it('places settings under Панель', () => {
    const panel = SIDEBAR_NAV_GROUPS.find((g) => g.label === 'Панель')
    expect(panel?.items.map((i) => i.to)).toEqual([
      '/nodes',
      '/settings',
      '/telegram',
      '/edit-files',
    ])
  })

  it('keeps network tools under Сеть', () => {
    const net = SIDEBAR_NAV_GROUPS.find((g) => g.label === 'Сеть')
    expect(net?.items.map((i) => i.to)).toEqual([
      '/routing',
      '/antizapret',
      '/proxy',
      '/warper',
      '/awg2',
    ])
  })

  it('keeps observe tools under Наблюдение', () => {
    const obs = SIDEBAR_NAV_GROUPS.find((g) => g.label === 'Наблюдение')
    expect(obs?.items.map((i) => i.to)).toEqual([
      '/monitoring',
      '/traffic',
      '/logs',
      '/server-monitor',
    ])
  })
})

describe('visibility', () => {
  it('hides adminOnly items for non-admin', () => {
    const nodes = SIDEBAR_NAV_GROUPS.flatMap((g) => g.items).find((i) => i.to === '/nodes')!
    expect(isSidebarNavItemVisible(nodes, 'user', () => true)).toBe(false)
    expect(isSidebarNavItemVisible(nodes, 'admin', () => true)).toBe(true)
  })

  it('drops empty groups when features off', () => {
    const groups = getVisibleSidebarNavGroups('admin', () => false)
    // home has featureKey null → still visible; subscription gated off
    expect(groups.some((g) => g.label === 'Клиенты')).toBe(true)
    expect(groups.find((g) => g.label === 'Клиенты')?.items.map((i) => i.to)).toEqual(['/'])
  })
})
