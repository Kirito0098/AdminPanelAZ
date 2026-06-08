import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getBackgroundTask } from '@/api/client'
import type { BackgroundTask } from '@/types'

const DEFAULT_INTERVAL_MS = 1500
const DEFAULT_TIMEOUT_MS = 900_000
const MAX_CONSECUTIVE_ERRORS = 3

export interface BackgroundTaskPollOptions {
  intervalMs?: number
  timeoutMs?: number
  onProgress?: (task: BackgroundTask) => void
  onComplete?: (task: BackgroundTask) => void
  onError?: (task: BackgroundTask | null, message: string) => void
}

export function useBackgroundTaskPoll() {
  const [task, setTask] = useState<BackgroundTask | null>(null)
  const [polling, setPolling] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startedAtRef = useRef<number>(0)
  const errorCountRef = useRef(0)
  const optionsRef = useRef<BackgroundTaskPollOptions>({})

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    setPolling(false)
  }, [])

  const pollOnce = useCallback(async (taskId: string) => {
    const opts = optionsRef.current
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS
    if (Date.now() - startedAtRef.current > timeoutMs) {
      stopPoll()
      opts.onError?.(task, 'Превышено время ожидания задачи')
      return
    }

    try {
      const current = await getBackgroundTask(taskId)
      errorCountRef.current = 0
      setTask(current)
      opts.onProgress?.(current)
      if (current.status === 'completed') {
        stopPoll()
        opts.onComplete?.(current)
      } else if (current.status === 'failed') {
        stopPoll()
        opts.onError?.(current, current.error || current.message || 'Задача завершилась с ошибкой')
      }
    } catch (err) {
      errorCountRef.current += 1
      if (errorCountRef.current >= MAX_CONSECUTIVE_ERRORS) {
        stopPoll()
        const message = err instanceof ApiError ? err.message : 'Ошибка отслеживания задачи'
        opts.onError?.(task, message)
      }
    }
  }, [stopPoll, task])

  const startPoll = useCallback(
    (taskId: string, options: BackgroundTaskPollOptions = {}) => {
      stopPoll()
      optionsRef.current = options
      startedAtRef.current = Date.now()
      errorCountRef.current = 0
      setPolling(true)
      setTask({
        task_id: taskId,
        task_type: '',
        status: 'queued',
        message: 'Задача поставлена в очередь',
        progress_percent: 0,
        progress_stage: 'Ожидание запуска...',
      })
      void pollOnce(taskId)
      pollRef.current = setInterval(() => {
        void pollOnce(taskId)
      }, options.intervalMs ?? DEFAULT_INTERVAL_MS)
    },
    [pollOnce, stopPoll],
  )

  useEffect(() => () => stopPoll(), [stopPoll])

  return { task, polling, startPoll, stopPoll }
}
