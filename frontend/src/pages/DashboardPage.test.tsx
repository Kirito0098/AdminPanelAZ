// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Node, User, VpnConfig } from '@/types'
import DashboardPage from './DashboardPage'

const nodeState = vi.hoisted(() => ({
  activeNode: null as Node | null,
  activeNodeHa: null,
  loading: true,
}))
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
const stable = vi.hoisted(() => ({
  notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  progress: {
    startGlobal: vi.fn(),
    doneGlobal: vi.fn(),
    withInline: vi.fn(),
    trackBackgroundTask: vi.fn(),
  },
  poll: { task: null, polling: false, startPoll: vi.fn() },
  modules: { isEnabled: () => true },
}))

const admin = { id: 7, username: 'admin', role: 'admin', theme: 'dark', is_active: true } as User

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: admin }) }))
vi.mock('@/context/NodeContext', () => ({ useNode: () => nodeState }))
vi.mock('@/context/FeatureModulesContext', () => ({ useFeatureModules: () => stable.modules }))
vi.mock('@/context/NotificationContext', () => ({ useNotifications: () => stable.notify }))
vi.mock('@/context/ProgressContext', () => ({ useProgress: () => stable.progress }))
vi.mock('@/hooks/useHaReplicaReadonly', () => ({ useHaReplicaReadonly: () => false }))
vi.mock('@/hooks/useBackgroundTaskPoll', () => ({ useBackgroundTaskPoll: () => stable.poll }))

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

const node = { id: 1, name: 'main', status: 'online', is_local: true } as unknown as Node

function renderPage() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  )
}

describe('DashboardPage initial load', () => {
  beforeEach(() => {
    nodeState.activeNode = null
    nodeState.loading = true
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
    const { rerender } = renderPage()
    await act(async () => {})

    nodeState.activeNode = node
    nodeState.loading = false
    rerender(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )
    await act(async () => {})
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
