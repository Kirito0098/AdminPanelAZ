// @vitest-environment jsdom
import { cleanup, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { mountWhileActiveNodeResolves, resetNodeState } from '@/test/nodePageHarness'
import type { VpnConfig } from '@/types'
import DashboardPage from './DashboardPage'

const api = vi.hoisted(() => ({
  getMonitoring: vi.fn(),
  getConfigs: vi.fn(),
  getAwg2Health: vi.fn(),
  getEffectiveVisibleVpnProfiles: vi.fn(),
  getClientPolicies: vi.fn(),
  getConfigProfileFiles: vi.fn(),
  getUsers: vi.fn(),
  getConfigTags: vi.fn(),
  getOpenVpnGroup: vi.fn(),
}))
const poll = vi.hoisted(() => ({ task: null, polling: false, startPoll: vi.fn() }))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/AuthContext', async () => (await import('@/test/nodePageHarness')).authModule)
vi.mock('@/context/NodeContext', async () => (await import('@/test/nodePageHarness')).nodeContextModule)
vi.mock('@/context/FeatureModulesContext', async () => (await import('@/test/nodePageHarness')).featureModulesModule)
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)
vi.mock('@/context/ProgressContext', async () => (await import('@/test/nodePageHarness')).progressModule)
vi.mock('@/hooks/useHaReplicaReadonly', () => ({ useHaReplicaReadonly: () => false }))
vi.mock('@/hooks/useBackgroundTaskPoll', () => ({ useBackgroundTaskPoll: () => poll }))

function config(id: number, clientName: string, vpnType: VpnConfig['vpn_type']): VpnConfig {
  return {
    id,
    client_name: clientName,
    vpn_type: vpnType,
    owner_id: 7,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    profile_files: [],
  }
}

describe('DashboardPage initial load', () => {
  beforeEach(() => {
    resetNodeState()
    api.getMonitoring.mockResolvedValue({ services: [], openvpn_clients: [], wireguard_peers: [], timestamp: '' })
    api.getConfigs.mockResolvedValue([
      config(1, 'alice', 'openvpn'),
      config(2, 'alice', 'wireguard'),
      config(3, 'bob', 'openvpn'),
    ])
    api.getAwg2Health.mockResolvedValue({ installed: true })
    api.getEffectiveVisibleVpnProfiles.mockResolvedValue({
      policy: { routes: [], protocols: ['openvpn', 'wireguard'], openvpn_groups: ['GROUP_UDP\\TCP'] },
      inherited: true,
    })
    api.getClientPolicies.mockResolvedValue({})
    api.getConfigProfileFiles.mockResolvedValue({})
    api.getUsers.mockResolvedValue([])
    api.getConfigTags.mockResolvedValue([])
    api.getOpenVpnGroup.mockResolvedValue({ group: 'GROUP_UDP\\TCP', options: [] })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('fetches every endpoint once while the active node resolves after mount', async () => {
    await mountWhileActiveNodeResolves(() => <DashboardPage />)
    await screen.findAllByText('alice')

    expect({
      monitoring: api.getMonitoring.mock.calls.length,
      configs: api.getConfigs.mock.calls.length,
      awg2Health: api.getAwg2Health.mock.calls.length,
      visibleProfiles: api.getEffectiveVisibleVpnProfiles.mock.calls.length,
      profileFiles: api.getConfigProfileFiles.mock.calls.length,
      policies: api.getClientPolicies.mock.calls,
    }).toEqual({
      monitoring: 1,
      configs: 1,
      awg2Health: 1,
      visibleProfiles: 1,
      profileFiles: 1,
      policies: [['alice,bob']],
    })
  })
})
