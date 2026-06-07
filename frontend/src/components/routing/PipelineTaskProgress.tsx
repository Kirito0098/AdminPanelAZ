import { AppProgress } from '@/components/ui/ProgressBar'
import type { CidrPipelineTask } from '@/types'
import { statusLabel } from './utils'

interface PipelineTaskProgressProps {
  task: CidrPipelineTask | null
}

export default function PipelineTaskProgress({ task }: PipelineTaskProgressProps) {
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
