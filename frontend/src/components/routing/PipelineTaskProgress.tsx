import BackgroundTaskProgress from '@/components/ui/BackgroundTaskProgress'
import type { CidrPipelineTask } from '@/types'

interface PipelineTaskProgressProps {
  task: CidrPipelineTask | null
}

export default function PipelineTaskProgress(props: PipelineTaskProgressProps) {
  return <BackgroundTaskProgress task={props.task} />
}
