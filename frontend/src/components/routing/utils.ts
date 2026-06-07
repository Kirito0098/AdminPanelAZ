export function formatDt(value?: string | null) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('ru-RU')
  } catch {
    return value
  }
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
