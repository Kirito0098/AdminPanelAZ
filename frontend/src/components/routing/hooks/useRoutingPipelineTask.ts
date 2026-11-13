import { useCallback, useEffect, useRef, useState } from 'react'
import type { MutableRefObject } from 'react'
import { useNotifications } from '@/context/NotificationContext'
import { usePipelineTaskPoll } from '@/components/routing/usePipelineTaskPoll'
import { getIngestKind, getPipelineStage, isPipelineRunning } from '@/components/routing/utils'
import type { CidrDbStatus, CidrPipelineTask } from '@/types'
import type { IngestKind, PipelinePendingAction, PipelineStage } from '@/components/routing/utils'
import type { LoadRouting, ReloadPipelineMeta } from './types'

interface Args {
  /** `load` from useRoutingData, late-bound: a finished pipeline task re-reads everything. */
  loadRef: MutableRefObject<LoadRouting>
  /** `loadPipelineMeta` from useRoutingData, late-bound: a failed task re-reads the panel only. */
  loadPipelineMetaRef: MutableRefObject<ReloadPipelineMeta>
}

/**
 * Pipeline task tracking shared by the data hook (auto-resume of an active task)
 * and the actions hook (starting a new one).
 *
 * It is declared before useRoutingData on purpose: loading meta needs to resume and sync
 * a task, while the task callbacks need the loaders — the loaders are passed as refs.
 */
export function useRoutingPipelineTask({ loadRef, loadPipelineMetaRef }: Args) {
  const { success, error: notifyError } = useNotifications()
  const {
    pipelineTask,
    pipelinePolling,
    startPipelinePoll,
    syncPipelineTask,
  } = usePipelineTaskPoll()

  const [pendingPipelineAction, setPendingPipelineAction] = useState<PipelinePendingAction | null>(null)
  /** Растёт после каждой завершённой задачи пайплайна: по нему UI перезапрашивает бюджет маршрутов. */
  const [lastTaskFinishedAt, setLastTaskFinishedAt] = useState(0)
  const [recentRollbackStamp, setRecentRollbackStamp] = useState<string | null>(null)
  const pendingRollbackStampRef = useRef<string | null>(null)
  const trackedTaskIdRef = useRef<string | null>(null)
  const pipelinePollingRef = useRef(false)

  useEffect(() => {
    pipelinePollingRef.current = pipelinePolling
  }, [pipelinePolling])

  const attachPipelineTask = useCallback(
    (
      taskId: string,
      stage: PipelineStage,
      okMsg: string,
      opts: { force?: boolean; initialTask?: CidrPipelineTask; ingestKind?: IngestKind } = {},
    ) => {
      const { force = false, initialTask, ingestKind } = opts
      if (!force && trackedTaskIdRef.current === taskId && pipelinePollingRef.current) return
      trackedTaskIdRef.current = taskId
      setPendingPipelineAction({ stage, ingestKind })
      startPipelinePoll(taskId, {
        initialTask,
        onComplete: (task) => {
          trackedTaskIdRef.current = null
          setPendingPipelineAction(null)
          setLastTaskFinishedAt(Date.now())
          success(okMsg)
          if (task.task_type === 'cidr_rollback') {
            const stamp =
              (typeof task.result?.backup_stamp === 'string' && task.result.backup_stamp) ||
              pendingRollbackStampRef.current
            if (stamp) setRecentRollbackStamp(stamp)
            pendingRollbackStampRef.current = null
          }
          void loadRef.current({ fullMeta: true })
        },
        onError: (task, message) => {
          trackedTaskIdRef.current = null
          setPendingPipelineAction(null)
          notifyError(task?.error || task?.message || message)
          void loadPipelineMetaRef.current()
        },
      })
    },
    [startPipelinePoll, success, notifyError, loadRef, loadPipelineMetaRef],
  )

  const resumeActivePipelineTask = useCallback(
    (activeTask: NonNullable<CidrDbStatus['active_task']>) => {
      if (!isPipelineRunning(activeTask)) return
      const stage = getPipelineStage(activeTask.task_type) ?? 1
      const ingestKind = getIngestKind(activeTask.task_type) ?? undefined
      attachPipelineTask(activeTask.task_id, stage, 'Операция обновления списков завершена', {
        initialTask: activeTask,
        ingestKind,
      })
    },
    [attachPipelineTask],
  )

  /** Adopt the active task reported by status: poll it again or just sync the shown progress. */
  const syncActivePipelineTask = useCallback(
    (activeTask: NonNullable<CidrDbStatus['active_task']>) => {
      if (trackedTaskIdRef.current !== activeTask.task_id || !pipelinePollingRef.current) {
        resumeActivePipelineTask(activeTask)
      } else {
        syncPipelineTask(activeTask)
      }
    },
    [resumeActivePipelineTask, syncPipelineTask],
  )

  return {
    pipelineTask,
    pendingPipelineAction,
    lastTaskFinishedAt,
    attachPipelineTask,
    syncActivePipelineTask,
    recentRollbackStamp,
    pendingRollbackStampRef,
  }
}
