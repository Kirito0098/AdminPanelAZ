import { describe, expect, it } from 'vitest'

import { buildDashboardSummary } from './dashboardSummary'
import type { MonitoringOverview } from '@/types'

const baseOverview = {
  scope: 'all',
  services: [],
  openvpn_clients: [],
  wireguard_peers: [],
  amneziawg2_peers: [],
  nodes_summary: [
    { node_id: 1, node_name: 'node-a', status: 'online', active_services: 4, total_services: 4 },
    { node_id: 2, node_name: 'node-b', status: 'online', active_services: 3, total_services: 4 },
  ],
  node_id: 1,
  node_name: 'node-a',
  server_ip: '203.0.113.10, 203.0.113.11',
} as unknown as MonitoringOverview

describe('buildDashboardSummary', () => {
  it('takes service counts of the active node when scope=all has no flat services', () => {
    const summary = buildDashboardSummary([], baseOverview, 'node-a')

    // Раньше карточка «VPN-службы» показывала 0/0: агрегат scope=all отдаёт services=[].
    expect(summary.active_services).toBe(4)
    expect(summary.total_services).toBe(4)
  })

  it('falls back to the flat services list when there is no nodes_summary', () => {
    const overview = {
      ...baseOverview,
      nodes_summary: undefined,
      services: [
        { name: 'openvpn-server@antizapret-udp', status: 'active', active: true },
        { name: 'wg-quick@antizapret', status: 'inactive', active: false },
      ],
    } as unknown as MonitoringOverview

    const summary = buildDashboardSummary([], overview)

    expect(summary.active_services).toBe(1)
    expect(summary.total_services).toBe(2)
  })

  it('keeps zeros without an overview', () => {
    const summary = buildDashboardSummary([], null, 'node-a')

    expect(summary.active_services).toBe(0)
    expect(summary.total_services).toBe(0)
  })
})
