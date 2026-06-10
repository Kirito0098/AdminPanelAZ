import { AppProgress } from '@/components/ui/ProgressBar'
import type { CidrPipelineTask } from '@/types'
import {
  isPipelineRunning,
  pipelineTaskStatusLabel,
  taskBelongsToStage,
  type IngestKind,
  type PipelineStage,
} from './utils'

interface PipelineStageProgressProps {
  task: CidrPipelineTask | null
  stage: PipelineStage
  ingestKind?: IngestKind
  starting?: boolean
}

export default function PipelineStageProgress({
  task,
  stage,
  ingestKind,
  starting = false,
}: PipelineStageProgressProps) {
  const activeTask = !!task && isPipelineRunning(task)
  const stageMatch = !!task && taskBelongsToStage(task, stage, ingestKind)
  const active = activeTask && stageMatch
  const visible = active || starting

  if (!visible) return null

  const stageLabel = task?.progress_stage || task?.message || 'Выполнение операции…'
  const statusSuffix = task ? pipelineTaskStatusLabel(task.status) : 'Запуск…'
  const label = starting && !activeTask ? 'Запуск задачи…' : `${stageLabel} · ${statusSuffix}`

  return (
    <AppProgress
      value={activeTask ? task!.progress_percent : null}
      label={label}
      icon
      className="mb-4"
    />
  )
}
