// @vitest-environment jsdom
import { act, cleanup, fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  mountWhileActiveNodeResolves,
  resetNodeState,
  testNode,
  updateNodeState,
} from '@/test/nodePageHarness'
import type { Node } from '@/types'
import MonitoringPage from './MonitoringPage'

const api = vi.hoisted(() => ({
  getMonitoring: vi.fn(),
  getNocIncidents: vi.fn(),
  getConnectionHistory: vi.fn(),
  getResourceHistory: vi.fn(),
  openMonitoringStream: vi.fn(),
}))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/AuthContext', async () => (await import('@/test/nodePageHarness')).authModule)
vi.mock('@/context/NodeContext', async () => (await import('@/test/nodePageHarness')).nodeContextModule)
vi.mock('@/context/FeatureModulesContext', async () => (await import('@/test/nodePageHarness')).featureModulesModule)
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)
vi.mock('@/context/ProgressContext', async () => (await import('@/test/nodePageHarness')).progressModule)
vi.mock('@/components/dashboard/GeoRoutingHintBanner', () => ({ default: () => null }))
vi.mock('@/components/monitoring/MonitoringCharts', () => ({ default: () => null }))
vi.mock('@/components/monitoring/ResourceHistoryCharts', () => ({ default: () => null }))
vi.mock('@/components/monitoring/PanelResourceHistoryCharts', () => ({ default: () => null }))

const secondNode = { ...testNode, id: 2, name: 'edge', is_local: false } as Node
const page = () => <MonitoringPage />

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
    resetNodeState()
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
    await mountWhileActiveNodeResolves(page, { nodes: [testNode] })

    expect(callCounts()).toEqual(once)
    expect(api.getMonitoring).toHaveBeenCalledWith('node', 'dedupe')
  })

  it('fetches once when the scope is already stored', async () => {
    window.localStorage.setItem('noc-monitoring:scope', 'node')

    await mountWhileActiveNodeResolves(page, { nodes: [testNode] })

    expect(callCounts()).toEqual(once)
  })

  describe('first visit with several nodes', () => {
    it('defaults to all nodes when the node list arrives after the active node', async () => {
      const result = await mountWhileActiveNodeResolves(page, { nodes: [], nodesLoading: true })

      expect(api.getMonitoring).not.toHaveBeenCalled()
      expect(window.localStorage.getItem('noc-monitoring:scope')).toBeNull()

      await updateNodeState(result, page, { nodes: [testNode, secondNode], nodesLoading: false })

      expect(callCounts()).toEqual(once)
      expect(api.getMonitoring).toHaveBeenCalledWith('all', 'dedupe')
      expect(api.getConnectionHistory).toHaveBeenCalledWith('1h', 'all')
      expect(window.localStorage.getItem('noc-monitoring:scope')).toBe('all')
    })

    it('defaults to all nodes when the node list arrives before the active node', async () => {
      await mountWhileActiveNodeResolves(page, { nodes: [testNode, secondNode], nodesLoading: false })

      expect(callCounts()).toEqual(once)
      expect(api.getMonitoring).toHaveBeenCalledWith('all', 'dedupe')
      expect(window.localStorage.getItem('noc-monitoring:scope')).toBe('all')
    })
  })
})

describe('MonitoringPage incidents', () => {
  const overview = { services: [], openvpn_clients: [], wireguard_peers: [], timestamp: '' }

  beforeEach(() => {
    window.localStorage.clear()
    resetNodeState()
    api.getMonitoring.mockResolvedValue(overview)
    api.getNocIncidents.mockResolvedValue({ items: [] })
    api.getConnectionHistory.mockResolvedValue({ points: [] })
    api.getResourceHistory.mockResolvedValue({ points: [] })
    api.openMonitoringStream.mockReturnValue({ close: vi.fn() })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('fetches once when the stream payload arrives before the overview', async () => {
    let resolveOverview: (value: typeof overview) => void = () => {}
    let resolveIncidents: (value: { items: [] }) => void = () => {}
    api.getMonitoring.mockReturnValue(new Promise((resolve) => (resolveOverview = resolve)))
    api.getNocIncidents.mockReturnValue(new Promise((resolve) => (resolveIncidents = resolve)))

    await mountWhileActiveNodeResolves(page, { nodes: [testNode] })
    const onPayload = api.openMonitoringStream.mock.calls[0][0] as (payload: typeof overview) => void
    await act(async () => onPayload(overview))
    expect(api.getNocIncidents).toHaveBeenCalledTimes(1)

    await act(async () => resolveOverview(overview))
    await act(async () => resolveIncidents({ items: [] }))

    expect(api.getNocIncidents).toHaveBeenCalledTimes(1)
  })

  it('refetches on manual refresh', async () => {
    await mountWhileActiveNodeResolves(page, { nodes: [testNode] })
    expect(api.getNocIncidents).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }))
    await act(async () => {})

    expect(api.getNocIncidents).toHaveBeenCalledTimes(2)
  })

  it('reuses the pending request on manual refresh', async () => {
    api.getNocIncidents.mockReturnValue(new Promise(() => {}))
    await mountWhileActiveNodeResolves(page, { nodes: [testNode] })

    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }))
    await act(async () => {})

    expect(api.getMonitoring).toHaveBeenCalledTimes(2)
    expect(api.getNocIncidents).toHaveBeenCalledTimes(1)
  })

  it('retries on manual refresh after a failed request', async () => {
    api.getNocIncidents.mockRejectedValueOnce(new Error('boom'))
    await mountWhileActiveNodeResolves(page, { nodes: [testNode] })
    expect(api.getNocIncidents).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }))
    await act(async () => {})

    expect(api.getNocIncidents).toHaveBeenCalledTimes(2)
  })

  it('does not refetch when the scope changes', async () => {
    await mountWhileActiveNodeResolves(page, { nodes: [testNode, secondNode] })
    expect(api.getNocIncidents).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Активный узел' }))
    await act(async () => {})

    expect(api.getMonitoring).toHaveBeenLastCalledWith('node', 'dedupe')
    expect(api.getNocIncidents).toHaveBeenCalledTimes(1)
  })

  it('refetches when the active node changes (service incidents belong to it)', async () => {
    const result = await mountWhileActiveNodeResolves(page, { nodes: [testNode, secondNode] })
    expect(api.getNocIncidents).toHaveBeenCalledTimes(1)

    await updateNodeState(result, page, { activeNode: secondNode })

    expect(api.getNocIncidents).toHaveBeenCalledTimes(2)
  })
})
