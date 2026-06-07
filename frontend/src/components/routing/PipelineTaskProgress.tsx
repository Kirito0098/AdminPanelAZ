import { Loader2 } from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import type { CidrPipelineTask } from '@/types'
import { statusLabel } from './utils'

interface PipelineTaskProgressProps {
  task: CidrPipelineTask | null
}

export default function PipelineTaskProgress({ task }: PipelineTaskProgressProps) {
  if (!task || !['queued', 'running'].includes(task.status)) return null

  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Loader2 size={16} className="animate-spin text-primary" />
        <span>{task.progress_stage || task.message || 'Выполнение задачи...'}</span>
        <span className="ml-auto text-muted-foreground">{statusLabel(task.status)}</span>
      </div>
      <div className="flex items-center gap-3">
        <Progress value={task.progress_percent} className="flex-1" />
        <span className="mono text-sm font-medium tabular-nums">{task.progress_percent}%</span>
      </div>
    </div>
  )
}
