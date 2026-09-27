// @vitest-environment jsdom
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { mountWhileActiveNodeResolves, resetNodeState } from '@/test/nodePageHarness'
import TrafficPage from './TrafficPage'

const api = vi.hoisted(() => ({
  getTrafficOverview: vi.fn(),
  getTrafficActiveClients: vi.fn(),
  getDeletedClientTraffic: vi.fn(),
  getNeverConnectedClientTraffic: vi.fn(),
  getTrafficCleanupSchedule: vi.fn(),
}))
const settingsApi = vi.hoisted(() => ({ getRetentionSettings: vi.fn() }))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/api/settings', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/settings')>()),
  ...settingsApi,
}))
vi.mock('@/context/AuthContext', async () => (await import('@/test/nodePageHarness')).authModule)
vi.mock('@/context/NodeContext', async () => (await import('@/test/nodePageHarness')).nodeContextModule)
vi.mock('@/context/FeatureModulesContext', async () => (await import('@/test/nodePageHarness')).featureModulesModule)
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)
vi.mock('@/context/ProgressContext', async () => (await import('@/test/nodePageHarness')).progressModule)

describe('TrafficPage initial load', () => {
  beforeEach(() => {
    resetNodeState()
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
    await mountWhileActiveNodeResolves(() => <TrafficPage />)

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
