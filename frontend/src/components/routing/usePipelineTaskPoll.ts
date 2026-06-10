import { getCidrBackgroundTask } from '@/api/client'
import { useBackgroundTaskPoll } from '@/hooks/useBackgroundTaskPoll'

/** Poll interval for long-running CIDR pipeline tasks (~3–10 min). */
export const PIPELINE_POLL_INTERVAL_MS = 3000

/** Pipeline-only task polling (isolated from global ProgressContext). */
export function usePipelineTaskPoll() {
  const poll = useBackgroundTaskPoll()

  const startPipelinePoll = (
    taskId: string,
    options: Parameters<typeof poll.startPoll>[1] = {},
  ) => {
    poll.startPoll(taskId, {
      intervalMs: PIPELINE_POLL_INTERVAL_MS,
      fetchTask: getCidrBackgroundTask,
      ...options,
    })
  }

  return {
    pipelineTask: poll.task,
    pipelinePolling: poll.polling,
    startPipelinePoll,
  }
}
