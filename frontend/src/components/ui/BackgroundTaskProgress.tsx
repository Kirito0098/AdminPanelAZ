import { AppProgress } from '@/components/ui/ProgressBar'
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
  if (!task || !['queued', 'running'].includes(task.status)) return null

  const label = task.progress_stage || task.message || 'Выполнение задачи...'

  return (
    <AppProgress
      value={task.progress_percent}
      label={`${label} · ${statusLabel(task.status)}`}
      icon
    />
  )
}
