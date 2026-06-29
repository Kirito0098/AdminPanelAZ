import {
  formatCompactCount,
  getPipelineStage,
} from '@/components/routing/utils'
import { STAGE_BUILD, STAGE_DEPLOY, STAGE_LOAD } from '@/components/routing/routingLabels'
import { formatDateTime } from '@/lib/datetime'
import type { TgMiniCidrStatus } from '@/types'

export type CidrRefreshTone = 'success' | 'warning' | 'error' | 'running' | 'idle'

export function cidrRefreshMeta(status?: string | null): { label: string; tone: CidrRefreshTone } {
  switch (status) {
    case 'ok':
      return { label: 'OK', tone: 'success' }
    case 'partial':
      return { label: 'Частично', tone: 'warning' }
    case 'error':
      return { label: 'Ошибка', tone: 'error' }
    case 'running':
      return { label: 'Выполняется', tone: 'running' }
    case 'never':
      return { label: 'Нет данных', tone: 'idle' }
    default:
      return { label: status ?? '—', tone: 'idle' }
  }
}

export function formatCidrCount(value: number): string {
  return formatCompactCount(value)
}

export function formatCidrDate(value?: string | null): string {
  if (!value) return '—'
  return formatDateTime(value)
}

export type PipelineStepState = 'done' | 'current' | 'pending' | 'warning'

export interface CidrPipelineStep {
  stage: 1 | 2 | 3
  label: string
  state: PipelineStepState
  summary: string
}

export function buildCidrPipelineSteps(data: TgMiniCidrStatus): CidrPipelineStep[] {
  const refresh = data.last_refresh_status
  const hasDb = (data.total_cidrs ?? 0) > 0
  const refreshOk = refresh === 'ok' || refresh === 'partial'
  const compile = data.last_compile
  const deploy = data.last_deploy
  const compileDone = compile?.status === 'completed'
  const deployDone =
    deploy?.status === 'completed' ||
    (typeof deploy?.nodes_deployed === 'number' && deploy.nodes_deployed > 0)

  const activeStage = data.pipeline_task?.task_type
    ? getPipelineStage(data.pipeline_task.task_type)
    : null
  const isRunning = ['queued', 'running'].includes(data.pipeline_task?.status ?? '')

  const stepState = (stage: 1 | 2 | 3, done: boolean): PipelineStepState => {
    if (isRunning && activeStage === stage) return 'current'
    if (done) return 'done'
    if (refresh === 'error' && stage === 1) return 'warning'
    if (compile?.status === 'failed' && stage === 2) return 'warning'
    if (deploy?.status === 'failed' && stage === 3) return 'warning'
    if (!done && activeStage === stage) return 'current'
    return 'pending'
  }

  return [
    {
      stage: 1,
      label: STAGE_LOAD,
      state: stepState(1, hasDb && refreshOk),
      summary: hasDb
        ? `${formatCidrCount(data.total_cidrs)} CIDR · ${cidrRefreshMeta(refresh).label}`
        : 'SQLite пуста',
    },
    {
      stage: 2,
      label: STAGE_BUILD,
      state: stepState(2, Boolean(compileDone || data.has_compile_artifacts)),
      summary: compileDone
        ? `Файлов: ${String(compile?.files_updated ?? '—')}`
        : data.has_compile_artifacts
          ? 'Артефакты готовы'
          : 'Сборка не выполнялась',
    },
    {
      stage: 3,
      label: STAGE_DEPLOY,
      state: stepState(3, Boolean(deployDone)),
      summary: deployDone
        ? `Узлов: ${String(deploy?.nodes_deployed ?? '—')}`
        : 'На узлы не выкладывали',
    },
  ]
}

export function pipelineTaskStatusLabel(status?: string | null): string {
  switch (status) {
    case 'queued':
      return 'В очереди'
    case 'running':
      return 'Выполняется'
    case 'completed':
      return 'Завершено'
    case 'failed':
      return 'Ошибка'
    default:
      return status ?? '—'
  }
}
