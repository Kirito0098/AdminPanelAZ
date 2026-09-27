// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Node, User } from '@/types'
import MonitoringPage from './MonitoringPage'

const nodeState = vi.hoisted(() => ({
  activeNode: null as Node | null,
  activeNodeHa: null,
  nodes: [] as Node[],
  loading: true,
  activate: vi.fn(),
}))
const api = vi.hoisted(() => ({
  getMonitoring: vi.fn(),
  getNocIncidents: vi.fn(),
  getConnectionHistory: vi.fn(),
  getResourceHistory: vi.fn(),
  openMonitoringStream: vi.fn(),
}))
const stable = vi.hoisted(() => ({
  notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  progress: { startGlobal: vi.fn(), doneGlobal: vi.fn() },
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
vi.mock('@/components/dashboard/GeoRoutingHintBanner', () => ({ default: () => null }))
vi.mock('@/components/monitoring/MonitoringCharts', () => ({ default: () => null }))
vi.mock('@/components/monitoring/ResourceHistoryCharts', () => ({ default: () => null }))
vi.mock('@/components/monitoring/PanelResourceHistoryCharts', () => ({ default: () => null }))

const node = { id: 1, name: 'main', status: 'online', is_local: true } as unknown as Node

function page() {
  return (
    <MemoryRouter>
      <MonitoringPage />
    </MemoryRouter>
  )
}

async function mountWhileActiveNodeResolves() {
  const { rerender } = render(page())
  await act(async () => {})
  nodeState.activeNode = node
  nodeState.nodes = [node]
  nodeState.loading = false
  rerender(page())
  await act(async () => {})
}

function callCounts() {
  return {
    overview: api.getMonitoring.mock.calls.length,
    incidents: api.getNocIncidents.mock.calls.length,
    connectionHistory: api.getConnectionHistory.mock.calls.length,
    resourceHistory: api.getResourceHistory.mock.calls.length,
    stream: api.openMonitoringStream.mock.calls.length,
  }
}

const once = { overview: 1, incidents: 1, connectionHistory: 1, resourceHistory: 1, stream: 1 }

describe('MonitoringPage initial load', () => {
  beforeEach(() => {
    window.localStorage.clear()
    nodeState.activeNode = null
    nodeState.nodes = []
    nodeState.loading = true
    api.getMonitoring.mockResolvedValue({ services: [], openvpn_clients: [], wireguard_peers: [], timestamp: '' })
    api.getNocIncidents.mockResolvedValue({ items: [] })
    api.getConnectionHistory.mockResolvedValue({ points: [] })
    api.getResourceHistory.mockResolvedValue({ points: [] })
    api.openMonitoringStream.mockReturnValue({ close: vi.fn() })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('fetches once on the first visit (scope not stored yet)', async () => {
    await mountWhileActiveNodeResolves()

    expect(callCounts()).toEqual(once)
    expect(api.getMonitoring).toHaveBeenCalledWith('node', 'dedupe')
  })

  it('fetches once when the scope is already stored', async () => {
    window.localStorage.setItem('noc-monitoring:scope', 'node')

    await mountWhileActiveNodeResolves()

    expect(callCounts()).toEqual(once)
  })
})
