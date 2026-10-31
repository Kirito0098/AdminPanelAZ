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
    { node_id: 1, node_name: 'Germani', status: 'online', active_services: 4, total_services: 4 },
    { node_id: 2, node_name: 'Test_serv', status: 'online', active_services: 3, total_services: 4 },
  ],
  node_id: 1,
  node_name: 'Germani',
  server_ip: '138.124.36.24, 138.124.37.133',
} as unknown as MonitoringOverview

describe('buildDashboardSummary', () => {
  it('takes service counts of the active node when scope=all has no flat services', () => {
    const summary = buildDashboardSummary([], baseOverview, 'Germani')

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
    const summary = buildDashboardSummary([], null, 'Germani')

    expect(summary.active_services).toBe(0)
    expect(summary.total_services).toBe(0)
  })
})
