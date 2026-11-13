import { AppProgress } from '@/components/ui/ProgressBar'
import type { CidrPipelineTask } from '@/types'
import { getPipelineStageMeta } from './routingWorkflow'
import {
  isPipelineRunning,
  statusLabel,
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

  const stageMeta = getPipelineStageMeta(stage)
  const stageLabel = task?.progress_stage || task?.message || stageMeta.description
  const statusSuffix = task ? statusLabel(task.status) : 'Запуск…'
  const overallPct =
    activeTask && task!.progress_percent != null && task!.progress_percent >= 0
      ? Math.min(100, Math.max(0, task!.progress_percent))
      : null
  const label =
    starting && !activeTask
      ? 'Запуск задачи…'
      : overallPct != null
        ? `${stageLabel} · ${statusSuffix} · общий ${overallPct}%`
        : `${stageLabel} · ${statusSuffix}`

  return (
    <AppProgress
      value={activeTask ? task!.progress_percent : null}
      label={label}
      icon
      className="mb-4"
    />
  )
}
