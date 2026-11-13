import { describe, expect, it } from 'vitest'

import { getRoutingWorkflowState, PIPELINE_STAGES } from './routingWorkflow'
import type { CidrDbStatus, CidrProviderInfo } from '@/types'

function provider(overrides: Partial<CidrProviderInfo> = {}): CidrProviderInfo {
  return {
    filename: 'cloudflare-ips.txt',
    name: 'Cloudflare',
    description: '',
    category: 'cdn',
    enabled: true,
    has_source: false,
    cidr_count: 0,
    ...overrides,
  }
}

function cidrDb(overrides: Partial<CidrDbStatus> = {}): CidrDbStatus {
  return {
    success: true,
    providers: {},
    total_cidrs: 0,
    last_refresh_status: 'never',
    ...overrides,
  } as CidrDbStatus
}

const withData = {
  providers: {
    'cloudflare-ips.txt': { cidr_count: 10, refresh_status: 'ok' },
  },
} as unknown as Partial<CidrDbStatus>

describe('PIPELINE_STAGES', () => {
  it('describes the three pipeline stages with unique anchors', () => {
    expect(PIPELINE_STAGES).toHaveLength(3)
    expect(PIPELINE_STAGES.map((stage) => stage.stage)).toEqual([1, 2, 3])
    expect(new Set(PIPELINE_STAGES.map((stage) => stage.id)).size).toBe(3)
    expect(PIPELINE_STAGES.every((stage) => stage.label && stage.shortLabel)).toBe(true)
  })
})

describe('getRoutingWorkflowState', () => {
  it('starts at stage 1 when there is no data at all', () => {
    const state = getRoutingWorkflowState([], null)

    expect(state.currentStage).toBe(1)
    expect(state.steps.map((step) => step.stage)).toEqual([1, 2, 3, 4])
    expect(state.steps[0].status).toBe('current')
    expect(state.steps[0].summary).toBe('Нет данных в SQLite')
    expect(state.nextAction).toMatchObject({ tab: 'pipeline', anchor: 'pipeline-stage-1' })
    expect(state.totalProviders).toBe(0)
    expect(state.enabledCount).toBe(0)
    expect(state.onNodeCount).toBe(0)
    expect(state.hasAlerts).toBe(false)
  })

  it('starts at stage 1 when the last ingest failed even with rows in the DB', () => {
    const state = getRoutingWorkflowState(
      [provider()],
      cidrDb({ total_cidrs: 42, last_refresh_status: 'error', ...withData }),
    )

    expect(state.currentStage).toBe(1)
    expect(state.steps[0].summary).toBe('Ошибка последнего ingest')
  })

  it('asks to build lists when DB data has no controller artifact yet', () => {
    const state = getRoutingWorkflowState(
      [provider()],
      cidrDb({ total_cidrs: 42, last_refresh_status: 'ok', ...withData, compile_artifacts: {} }),
    )

    expect(state.currentStage).toBe(2)
    expect(state.pendingCompileCount).toBe(1)
    expect(state.pendingCompileNames).toEqual(['Cloudflare'])
    expect(state.steps[1].status).toBe('current')
    expect(state.nextAction?.anchor).toBe('pipeline-stage-2')
  })

  it('prioritizes deploy when a fresh build is already on the controller', () => {
    const state = getRoutingWorkflowState(
      [provider({ enabled: true, has_source: false })],
      cidrDb({
        total_cidrs: 42,
        last_refresh_status: 'ok',
        ...withData,
        compile_artifacts: { 'cloudflare-ips.txt': { cidr_count: 10, exists: true } },
        last_compile_at: { status: 'completed', finished_at: '2026-01-01T00:00:00Z', files_updated: 1 },
      }),
    )

    expect(state.currentStage).toBe(3)
    expect(state.pendingDeployCount).toBe(1)
    expect(state.pendingCompileCount).toBe(0)
    expect(state.compileRecentlyCompleted).toBe(true)
    expect(state.steps[2].status).toBe('current')
    expect(state.nextAction?.anchor).toBe('pipeline-stage-3')
  })

  it('is done when everything is built, deployed and enabled', () => {
    const state = getRoutingWorkflowState(
      [provider({ enabled: true, has_source: true })],
      cidrDb({
        total_cidrs: 42,
        last_refresh_status: 'ok',
        providers: { 'cloudflare-ips.txt': { cidr_count: 10, refresh_status: 'ok' } },
        compile_artifacts: { 'cloudflare-ips.txt': { cidr_count: 10, exists: true } },
        last_compile_at: { status: 'completed', finished_at: '2026-01-01T00:00:00Z', files_updated: 1 },
        last_deploy: { status: 'completed', finished_at: '2026-01-01T01:00:00Z' },
      } as unknown as Partial<CidrDbStatus>),
    )

    expect(state.currentStage).toBeNull()
    expect(state.nextAction).toBeNull()
    expect(state.steps.every((step) => step.status === 'done')).toBe(true)
    expect(state.steps[3].summary).toBe('1 из 1 включено для маршрутизации')
  })

  it('asks to pick providers when lists are on the node but nothing is enabled', () => {
    const state = getRoutingWorkflowState(
      [provider({ enabled: false, has_source: true })],
      cidrDb({
        total_cidrs: 42,
        last_refresh_status: 'ok',
        ...withData,
        compile_artifacts: { 'cloudflare-ips.txt': { cidr_count: 10, exists: true } },
        last_compile_at: { status: 'completed', finished_at: '2026-01-01T00:00:00Z', files_updated: 1 },
      }),
    )

    expect(state.currentStage).toBe(4)
    expect(state.nextAction).toMatchObject({ tab: 'providers' })
  })

  it('escalates to stage 1 when alerts are present and nothing else is pending', () => {
    const state = getRoutingWorkflowState(
      [],
      cidrDb({
        total_cidrs: 0,
        last_refresh_status: 'never',
        alerts: [{ level: 'warning', message: 'stale data' }],
      } as unknown as Partial<CidrDbStatus>),
    )

    expect(state.currentStage).toBe(1)
    expect(state.hasAlerts).toBe(true)
    expect(state.steps[0].status).toBe('warning')
  })
})
