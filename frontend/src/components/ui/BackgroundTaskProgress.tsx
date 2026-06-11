import { createPortal } from 'react-dom'
import { Loader2 } from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import type { BackgroundTask } from '@/types'

interface BackgroundTaskProgressProps {
  task: BackgroundTask | null
}

function statusLabel(status: BackgroundTask['status']): string {
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

export default function BackgroundTaskProgress({ task }: BackgroundTaskProgressProps) {
  if (!task || !['queued', 'running'].includes(task.status) || typeof document === 'undefined') {
    return null
  }

  const stageLabel = task.progress_stage || task.message || 'Выполнение задачи...'
  const value =
    task.progress_percent != null && task.progress_percent >= 0
      ? Math.min(100, Math.max(0, task.progress_percent))
      : undefined
  const label = value != null
    ? `${stageLabel} · ${statusLabel(task.status)} · общий ${value}%`
    : `${stageLabel} · ${statusLabel(task.status)}`

  return createPortal(
    <div
      className="pointer-events-none fixed inset-x-0 bottom-0 z-[99] border-t border-primary/20 bg-background/95 px-4 py-3 shadow-[0_-8px_30px_rgba(0,0,0,0.12)] backdrop-blur-md supports-[backdrop-filter]:bg-background/85"
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={label}
    >
      <div className="mx-auto flex w-full max-w-4xl items-center gap-3">
        <Loader2 size={16} className="shrink-0 animate-spin text-primary" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">{label}</p>
          {value != null && (
            <Progress value={value} className="mt-2 h-1.5" />
          )}
        </div>
        {value != null && (
          <span className="shrink-0 text-sm font-medium tabular-nums text-muted-foreground">
            {value}%
          </span>
        )}
      </div>
    </div>,
    document.body,
  )
}
