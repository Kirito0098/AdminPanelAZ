// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Node } from '@/types'
import AntizapretConfigTab from './AntizapretConfigTab'

const nodeState = vi.hoisted(() => ({
  activeNode: null as Node | null,
  activeNodeHa: null,
  loading: true,
}))
const api = vi.hoisted(() => ({
  getAntizapretSettings: vi.fn(),
  getVpnNetworkSettings: vi.fn(),
}))
const stable = vi.hoisted(() => ({
  notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  progress: { trackBackgroundTask: vi.fn() },
}))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/NodeContext', () => ({ useNode: () => nodeState }))
vi.mock('@/context/NotificationContext', () => ({ useNotifications: () => stable.notify }))
vi.mock('@/context/ProgressContext', () => ({ useProgress: () => stable.progress }))
vi.mock('@/hooks/useHaReplicaReadonly', () => ({ useHaReplicaReadonly: () => false }))
vi.mock('@/components/routing/OpenVpnPanelTab', () => ({ default: () => null }))

const node = { id: 1, name: 'main', status: 'online', is_local: true } as unknown as Node

function page() {
  return (
    <MemoryRouter>
      <AntizapretConfigTab />
    </MemoryRouter>
  )
}

describe('AntizapretConfigTab initial load', () => {
  beforeEach(() => {
    nodeState.activeNode = null
    nodeState.loading = true
    api.getAntizapretSettings.mockResolvedValue({ schema: [], settings: {}, node_name: 'main' })
    api.getVpnNetworkSettings.mockResolvedValue({ env_rows: [] })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('loads AntiZapret and VPN network settings once while the active node resolves after mount', async () => {
    const { rerender } = render(page())
    await act(async () => {})
    nodeState.activeNode = node
    nodeState.loading = false
    rerender(page())
    await act(async () => {})

    expect({
      antizapretSettings: api.getAntizapretSettings.mock.calls.length,
      vpnNetwork: api.getVpnNetworkSettings.mock.calls.length,
    }).toEqual({ antizapretSettings: 1, vpnNetwork: 1 })
  })
})
