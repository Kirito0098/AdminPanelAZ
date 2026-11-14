import { describe, expect, it } from 'vitest'

import {
  getIngestKind,
  getPipelineStage,
  pendingMatchesStage,
  statusLabel,
  statusMeta,
  taskBelongsToStage,
} from './utils'

describe('statusLabel', () => {
  it.each([
    ['success', 'Успех'],
    ['skipped', 'Пропущен'],
    ['cancelled', 'Отменено'],
    ['unknown-status', 'Неизвестно'],
    ['', '—'],
    [null, '—'],
  ])('maps %s to %s', (status, expected) => {
    expect(statusLabel(status)).toBe(expected)
  })

  it('keeps the badge variant in sync with the label', () => {
    expect(statusMeta('cancelled')).toEqual({ label: 'Отменено', badge: 'outline' })
    expect(statusMeta('success').badge).toBe('success')
    expect(statusMeta('unknown-status').badge).toBe('outline')
  })
})

describe('pendingMatchesStage', () => {
  it('rejects an empty pending action', () => {
    expect(pendingMatchesStage(null, 1)).toBe(false)
  })

  it('rejects another stage', () => {
    expect(pendingMatchesStage({ stage: 2 }, 3)).toBe(false)
  })

  it('matches stage 2 and 3 regardless of ingest kind', () => {
    expect(pendingMatchesStage({ stage: 2 }, 2, 'providers')).toBe(true)
    expect(pendingMatchesStage({ stage: 3 }, 3, 'antifilter')).toBe(true)
  })

  it('splits stage 1 by ingest kind', () => {
    expect(pendingMatchesStage({ stage: 1, ingestKind: 'antifilter' }, 1)).toBe(true)
    expect(pendingMatchesStage({ stage: 1, ingestKind: 'antifilter' }, 1, 'antifilter')).toBe(true)
    expect(pendingMatchesStage({ stage: 1, ingestKind: 'antifilter' }, 1, 'providers')).toBe(false)
    expect(pendingMatchesStage({ stage: 1 }, 1, 'providers')).toBe(false)
  })
})

describe('stage task types', () => {
  it('maps task types to numeric stages', () => {
    expect(getPipelineStage('cidr_db_refresh')).toBe(1)
    expect(getPipelineStage('cidr_db_refresh_dry_run')).toBe(1)
    expect(getPipelineStage('antifilter_refresh')).toBe(1)
    expect(getPipelineStage('cidr_generate_from_db')).toBe(2)
    expect(getPipelineStage('cidr_estimate_from_db')).toBe(2)
    expect(getPipelineStage('cidr_rollback')).toBe(2)
    expect(getPipelineStage('cidr_deploy')).toBe(3)
  })

  it('taskBelongsToStage matches a running task of the same stage', () => {
    expect(taskBelongsToStage({ task_type: 'cidr_deploy' }, 3)).toBe(true)
    expect(taskBelongsToStage({ task_type: 'antifilter_refresh' }, 1, 'antifilter')).toBe(true)
    expect(taskBelongsToStage({ task_type: 'cidr_db_refresh' }, 1, 'providers')).toBe(true)
  })

  it('returns null for unknown or empty task types', () => {
    expect(getPipelineStage('doall')).toBeNull()
    expect(getPipelineStage('')).toBeNull()
    expect(getPipelineStage(undefined)).toBeNull()
    expect(getPipelineStage(null)).toBeNull()
  })

  it('rejects null tasks and tasks of another stage', () => {
    expect(taskBelongsToStage(null, 1)).toBe(false)
    expect(taskBelongsToStage({ task_type: 'cidr_deploy' }, 2)).toBe(false)
    expect(taskBelongsToStage({ task_type: 'cidr_db_refresh' }, 1, 'antifilter')).toBe(false)
  })

  it('separates ingest kinds', () => {
    expect(getIngestKind('cidr_db_refresh')).toBe('providers')
    expect(getIngestKind('cidr_db_refresh_dry_run')).toBe('providers')
    expect(getIngestKind('antifilter_refresh')).toBe('antifilter')
    expect(getIngestKind('cidr_deploy')).toBeNull()
    expect(getIngestKind('')).toBeNull()
  })
})
