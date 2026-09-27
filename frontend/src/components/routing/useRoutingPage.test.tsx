// @vitest-environment jsdom
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { mountWhileActiveNodeResolves, resetNodeState } from '@/test/nodePageHarness'
import { useRoutingPage } from './useRoutingPage'

const api = vi.hoisted(() => ({
  getRoutingOverview: vi.fn(),
  getCidrDbStatus: vi.fn(),
  getAntifilterStatus: vi.fn(),
  getCidrDbStatusSummary: vi.fn(),
}))
const pipelinePoll = vi.hoisted(() => ({
  pipelineTask: null,
  pipelinePolling: false,
  startPipelinePoll: vi.fn(),
  syncPipelineTask: vi.fn(),
}))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/NodeContext', async () => (await import('@/test/nodePageHarness')).nodeContextModule)
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)
vi.mock('@/context/ProgressContext', async () => (await import('@/test/nodePageHarness')).progressModule)
vi.mock('@/components/routing/usePipelineTaskPoll', () => ({ usePipelineTaskPoll: () => pipelinePoll }))

function RoutingProbe() {
  useRoutingPage()
  return null
}

describe('useRoutingPage initial load', () => {
  beforeEach(() => {
    resetNodeState()
    api.getRoutingOverview.mockResolvedValue({ providers: [] })
    api.getCidrDbStatus.mockResolvedValue({ total_cidrs: 0, active_task: null })
    api.getAntifilterStatus.mockResolvedValue({})
    api.getCidrDbStatusSummary.mockResolvedValue({ total_cidrs: 0, active_task: null })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('loads the routing overview and CIDR status once while the active node resolves after mount', async () => {
    await mountWhileActiveNodeResolves(() => <RoutingProbe />)

    expect({
      overview: api.getRoutingOverview.mock.calls.length,
      cidrDbStatus: api.getCidrDbStatus.mock.calls.length,
      antifilterStatus: api.getAntifilterStatus.mock.calls.length,
    }).toEqual({ overview: 1, cidrDbStatus: 1, antifilterStatus: 1 })
  })
})
