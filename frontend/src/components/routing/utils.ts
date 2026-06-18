import { formatDateTime } from '@/lib/datetime'

export function formatDt(value?: string | null) {
  if (!value) return '—'
  return formatDateTime(value, undefined, value)
}

export function statusBadgeVariant(status?: string | null) {
  if (status === 'ok') return 'default' as const
  if (status === 'partial') return 'secondary' as const
  if (status === 'error') return 'destructive' as const
  if (status === 'running') return 'secondary' as const
  return 'outline' as const
}

export function statusLabel(status?: string | null) {
  const map: Record<string, string> = {
    ok: 'OK',
    partial: 'Частично',
    error: 'Ошибка',
    running: 'Выполняется',
    never: 'Нет данных',
    queued: 'В очереди',
    completed: 'Завершено',
    failed: 'Сбой',
  }
  return map[status ?? ''] ?? status ?? '—'
}

export function isPipelineRunning(task: { status: string } | null) {
  return !!task && ['queued', 'running'].includes(task.status)
}

export type PipelineStage = 1 | 2 | 3

export type IngestKind = 'providers' | 'antifilter'

export type PipelinePendingAction = {
  stage: PipelineStage
  ingestKind?: IngestKind
}

const STAGE_TASK_TYPES: Record<PipelineStage, readonly string[]> = {
  1: ['cidr_db_refresh', 'cidr_db_refresh_dry_run', 'antifilter_refresh'],
  2: ['cidr_generate_from_db', 'cidr_estimate_from_db', 'cidr_rollback'],
  3: ['cidr_deploy'],
}

const INGEST_TASK_TYPES: Record<IngestKind, readonly string[]> = {
  providers: ['cidr_db_refresh', 'cidr_db_refresh_dry_run'],
  antifilter: ['antifilter_refresh'],
}

export function getIngestKind(taskType: string | undefined | null): IngestKind | null {
  const normalized = String(taskType || '').trim()
  for (const [kind, types] of Object.entries(INGEST_TASK_TYPES) as [IngestKind, readonly string[]][]) {
    if (types.includes(normalized)) return kind
  }
  return null
}

export function getPipelineStage(taskType: string | undefined | null): PipelineStage | null {
  const normalized = String(taskType || '').trim()
  if (!normalized) return null
  for (const [stage, types] of Object.entries(STAGE_TASK_TYPES) as [PipelineStage, readonly string[]][]) {
    if (types.includes(normalized)) return stage
  }
  return null
}

export function taskBelongsToStage(
  task: { task_type?: string | null } | null,
  stage: PipelineStage,
  ingestKind?: IngestKind,
): boolean {
  if (!task) return false
  if (getPipelineStage(task.task_type) !== stage) return false
  if (stage === 1 && ingestKind) {
    return getIngestKind(task.task_type) === ingestKind
  }
  return true
}

export function pendingMatchesStage(
  pending: PipelinePendingAction | null,
  stage: PipelineStage,
  ingestKind?: IngestKind,
): boolean {
  if (!pending || pending.stage !== stage) return false
  if (stage === 1 && ingestKind) return pending.ingestKind === ingestKind
  return true
}

export function pipelineTaskStatusLabel(status: string): string {
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
      return status
  }
}

/** Internal list key, e.g. digitalocean-ips.txt → digitalocean */
export function providerSlug(filename: string): string {
  if (filename.endsWith('-ips.txt')) return filename.slice(0, -'-ips.txt'.length)
  if (filename.endsWith('.txt')) return filename.slice(0, -4)
  return filename
}

export function providerCategoryLabel(category: string): string {
  const map: Record<string, string> = {
    cdn: 'CDN',
    cloud: 'Облако',
    hosting: 'Хостинг',
  }
  return map[category] ?? category
}

export function formatCompactCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (value >= 10_000) return `${Math.round(value / 1000)}k`
  if (value >= 1_000) return `${(value / 1000).toFixed(1).replace(/\.0$/, '')}k`
  return value.toLocaleString('ru-RU')
}

/** «1 провайдер», «2 провайдера», «5 провайдеров» */
export function pluralProviders(count: number): string {
  const abs = Math.abs(count)
  const mod100 = abs % 100
  const mod10 = abs % 10
  let word = 'провайдеров'
  if (mod100 < 11 || mod100 > 14) {
    if (mod10 === 1) word = 'провайдер'
    else if (mod10 >= 2 && mod10 <= 4) word = 'провайдера'
  }
  return `${count} ${word}`
}

/** «1 файл», «2 файла», «5 файлов» */
export function pluralFiles(count: number): string {
  const abs = Math.abs(count)
  const mod100 = abs % 100
  const mod10 = abs % 10
  let word = 'файлов'
  if (mod100 < 11 || mod100 > 14) {
    if (mod10 === 1) word = 'файл'
    else if (mod10 >= 2 && mod10 <= 4) word = 'файла'
  }
  return `${count} ${word}`
}

const BACKUP_STAMP_RE = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?$/

export function parseBackupDate(stamp: string, mtime?: number): Date | null {
  if (mtime != null && mtime > 0) {
    return new Date(mtime * 1000)
  }
  const match = BACKUP_STAMP_RE.exec(stamp.trim())
  if (!match) return null
  return new Date(
    Date.UTC(+match[1], +match[2] - 1, +match[3], +match[4], +match[5], +match[6]),
  )
}

export function formatBackupLabel(stamp: string, mtime?: number): string {
  const date = parseBackupDate(stamp, mtime)
  if (!date) return stamp
  return formatDateTime(date, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }, stamp)
}

export function formatBackupRelative(stamp: string, mtime?: number): string {
  const date = parseBackupDate(stamp, mtime)
  if (!date) return ''
  const diffMin = Math.floor((Date.now() - date.getTime()) / 60_000)
  if (diffMin < 1) return 'только что'
  if (diffMin < 60) return `${diffMin} мин. назад`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH} ч. назад`
  return `${Math.floor(diffH / 24)} дн. назад`
}

export function providerStatusTone(status?: string | null): 'ok' | 'warn' | 'error' | 'muted' {
  if (status === 'ok') return 'ok'
  if (status === 'partial') return 'warn'
  if (status === 'error') return 'error'
  return 'muted'
}
