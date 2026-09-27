// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Node, User } from '@/types'
import TrafficPage from './TrafficPage'

const nodeState = vi.hoisted(() => ({
  activeNode: null as Node | null,
  loading: true,
}))
const api = vi.hoisted(() => ({
  getTrafficOverview: vi.fn(),
  getTrafficActiveClients: vi.fn(),
  getDeletedClientTraffic: vi.fn(),
  getNeverConnectedClientTraffic: vi.fn(),
  getTrafficCleanupSchedule: vi.fn(),
}))
const settingsApi = vi.hoisted(() => ({ getRetentionSettings: vi.fn() }))
const stable = vi.hoisted(() => ({
  notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  progress: { startGlobal: vi.fn(), doneGlobal: vi.fn(), withInline: vi.fn() },
  modules: { isEnabled: () => true },
}))

const admin = { id: 7, username: 'admin', role: 'admin', theme: 'dark', is_active: true } as User

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/api/settings', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/settings')>()),
  ...settingsApi,
}))
vi.mock('@/context/AuthContext', () => ({ useAuth: () => ({ user: admin }) }))
vi.mock('@/context/NodeContext', () => ({ useNode: () => nodeState }))
vi.mock('@/context/FeatureModulesContext', () => ({ useFeatureModules: () => stable.modules }))
vi.mock('@/context/NotificationContext', () => ({ useNotifications: () => stable.notify }))
vi.mock('@/context/ProgressContext', () => ({ useProgress: () => stable.progress }))

const node = { id: 1, name: 'main', status: 'online', is_local: true } as unknown as Node

function page() {
  return (
    <MemoryRouter>
      <TrafficPage />
    </MemoryRouter>
  )
}

describe('TrafficPage initial load', () => {
  beforeEach(() => {
    nodeState.activeNode = null
    nodeState.loading = true
    api.getTrafficOverview.mockResolvedValue({
      rows: [],
      summary: { users_count: 0, total_bytes: 0 },
      retention_days: 30,
    })
    api.getTrafficActiveClients.mockResolvedValue({ active_clients: [] })
    api.getDeletedClientTraffic.mockResolvedValue({ rows: [], summary: { users_count: 0, total_bytes: 0 } })
    api.getNeverConnectedClientTraffic.mockResolvedValue({ rows: [], summary: { users_count: 0, rows_count: 0 } })
    api.getTrafficCleanupSchedule.mockResolvedValue({ period: 'none', openvpn_log_enabled: false })
    settingsApi.getRetentionSettings.mockResolvedValue({ traffic_sample_retention_days: 30 })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('fetches every endpoint once while the active node resolves after mount', async () => {
    const { rerender } = render(page())
    await act(async () => {})
    nodeState.activeNode = node
    nodeState.loading = false
    rerender(page())
    await act(async () => {})

    expect({
      overview: api.getTrafficOverview.mock.calls.length,
      activeClients: api.getTrafficActiveClients.mock.calls.length,
      deleted: api.getDeletedClientTraffic.mock.calls.length,
      neverConnected: api.getNeverConnectedClientTraffic.mock.calls.length,
      cleanupSchedule: api.getTrafficCleanupSchedule.mock.calls.length,
      retention: settingsApi.getRetentionSettings.mock.calls.length,
    }).toEqual({
      overview: 1,
      activeClients: 1,
      deleted: 1,
      neverConnected: 1,
      cleanupSchedule: 1,
      retention: 1,
    })
  })
})
