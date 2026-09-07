import { describe, expect, it } from 'vitest'

import type { MonitoringOverview, VpnConfig } from '@/types'

import {
  buildDashboardSummary,
  dashboardSummaryFromConfigs,
  mergeDashboardSummaryMonitoring,
} from './dashboardSummary'

function config(partial: Partial<VpnConfig> & Pick<VpnConfig, 'id' | 'client_name' | 'vpn_type'>): VpnConfig {
  return {
    owner_id: 1,
    created_at: '',
    updated_at: '',
    profile_files: [],
    ...partial,
  }
}

function overview(partial: Partial<MonitoringOverview>): MonitoringOverview {
  return {
    services: [],
    openvpn_clients: [],
    wireguard_peers: [],
    timestamp: '',
    ...partial,
  }
}

describe('dashboardSummaryFromConfigs', () => {
  it('counts openvpn and wireguard configs only', () => {
    const summary = dashboardSummaryFromConfigs(
      [
        config({ id: 1, client_name: 'a', vpn_type: 'openvpn' }),
        config({ id: 2, client_name: 'b', vpn_type: 'wireguard' }),
        config({ id: 3, client_name: 'c', vpn_type: 'amneziawg2' }),
      ],
      'node-a',
    )
    expect(summary).toEqual({
      total_configs: 3,
      openvpn_configs: 1,
      wireguard_configs: 1,
      connected_openvpn: 0,
      connected_wireguard: 0,
      active_services: 0,
      total_services: 0,
      server_ip: '',
      node_name: 'node-a',
    })
  })
})

describe('mergeDashboardSummaryMonitoring', () => {
  it('prefers overview totals and service fields', () => {
    const base = dashboardSummaryFromConfigs(
      [config({ id: 1, client_name: 'a', vpn_type: 'openvpn' })],
      'local',
    )
    const merged = mergeDashboardSummaryMonitoring(
      base,
      overview({
        total_connected_openvpn: 4,
        total_connected_wireguard: 2,
        server_ip: '1.2.3.4',
        node_name: 'edge',
        services: [
          { name: 'openvpn', status: 'active', active: true },
          { name: 'wg', status: 'inactive', active: false },
        ],
      }),
    )
    expect(merged.connected_openvpn).toBe(4)
    expect(merged.connected_wireguard).toBe(2)
    expect(merged.active_services).toBe(1)
    expect(merged.total_services).toBe(2)
    expect(merged.server_ip).toBe('1.2.3.4')
    expect(merged.node_name).toBe('edge')
    expect(merged.total_configs).toBe(1)
  })

  it('returns base when overview is missing', () => {
    const base = dashboardSummaryFromConfigs([], 'n')
    expect(mergeDashboardSummaryMonitoring(base, null)).toEqual(base)
  })
})

describe('buildDashboardSummary', () => {
  it('combines configs and overview in one shot', () => {
    const summary = buildDashboardSummary(
      [config({ id: 1, client_name: 'a', vpn_type: 'wireguard' })],
      overview({
        total_connected_openvpn: 0,
        total_connected_wireguard: 1,
        server_ip: '10.0.0.1',
      }),
      'fallback-name',
    )
    expect(summary.wireguard_configs).toBe(1)
    expect(summary.connected_wireguard).toBe(1)
    expect(summary.server_ip).toBe('10.0.0.1')
  })
})
