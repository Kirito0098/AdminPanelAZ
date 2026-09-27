// @vitest-environment jsdom
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { mountWhileActiveNodeResolves, resetNodeState } from '@/test/nodePageHarness'
import AntizapretConfigTab from './AntizapretConfigTab'

const api = vi.hoisted(() => ({
  getAntizapretSettings: vi.fn(),
  getVpnNetworkSettings: vi.fn(),
}))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/NodeContext', async () => (await import('@/test/nodePageHarness')).nodeContextModule)
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)
vi.mock('@/context/ProgressContext', async () => (await import('@/test/nodePageHarness')).progressModule)
vi.mock('@/hooks/useHaReplicaReadonly', () => ({ useHaReplicaReadonly: () => false }))
vi.mock('@/components/routing/OpenVpnPanelTab', () => ({ default: () => null }))

describe('AntizapretConfigTab initial load', () => {
  beforeEach(() => {
    resetNodeState()
    api.getAntizapretSettings.mockResolvedValue({ schema: [], settings: {}, node_name: 'main' })
    api.getVpnNetworkSettings.mockResolvedValue({ env_rows: [] })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('loads AntiZapret and VPN network settings once while the active node resolves after mount', async () => {
    await mountWhileActiveNodeResolves(() => <AntizapretConfigTab />)

    expect({
      antizapretSettings: api.getAntizapretSettings.mock.calls.length,
      vpnNetwork: api.getVpnNetworkSettings.mock.calls.length,
    }).toEqual({ antizapretSettings: 1, vpnNetwork: 1 })
  })
})
