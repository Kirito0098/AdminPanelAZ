import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getBackgroundTask } from '@/api/client'
import type { BackgroundTask } from '@/types'

const DEFAULT_INTERVAL_MS = 1500
const DEFAULT_TIMEOUT_MS = 900_000
const MAX_CONSECUTIVE_ERRORS = 3

export type BackgroundTaskFetcher = (taskId: string) => Promise<BackgroundTask>

export interface BackgroundTaskPollOptions {
  intervalMs?: number
  timeoutMs?: number
  fetchTask?: BackgroundTaskFetcher
  initialTask?: BackgroundTask
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
  const taskRef = useRef<BackgroundTask | null>(null)
  const pollOnceRef = useRef<(taskId: string) => Promise<void>>(async () => {})
  const errorNotifiedRef = useRef(false)

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
      opts.onError?.(taskRef.current, 'Превышено время ожидания задачи')
      return
    }

    try {
      const fetchTask = opts.fetchTask ?? getBackgroundTask
      const current = await fetchTask(taskId)
      if (!current?.task_id) {
        throw new ApiError('Некорректный ответ сервера о статусе задачи', 500)
      }
      errorCountRef.current = 0
      taskRef.current = current
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
      const isRateLimit = err instanceof ApiError && err.status === 429
      const message = err instanceof ApiError ? err.message : 'Ошибка отслеживания задачи'
      setTask((prev) =>
        prev
          ? {
              ...prev,
              progress_stage: isRateLimit
                ? 'Слишком много запросов, повтор через несколько секунд…'
                : `Ошибка опроса: ${message}`,
              message: isRateLimit ? 'Слишком много запросов' : message,
            }
          : prev,
      )
      if (isRateLimit) {
        return
      }
      errorCountRef.current += 1
      if (errorCountRef.current >= MAX_CONSECUTIVE_ERRORS) {
        stopPoll()
        if (!errorNotifiedRef.current) {
          errorNotifiedRef.current = true
          opts.onError?.(taskRef.current, message)
        }
      }
    }
  }, [stopPoll])

  pollOnceRef.current = pollOnce

  const startPoll = useCallback(
    (taskId: string, options: BackgroundTaskPollOptions = {}) => {
      stopPoll()
      optionsRef.current = options
      startedAtRef.current = Date.now()
      errorCountRef.current = 0
      errorNotifiedRef.current = false
      setPolling(true)
      setTask(
        options.initialTask ?? {
          task_id: taskId,
          task_type: '',
          status: 'queued',
          message: 'Запрос статуса задачи…',
          progress_percent: 0,
          progress_stage: 'Подключение к серверу…',
        },
      )
      const tick = () => {
        void pollOnceRef.current(taskId)
      }
      tick()
      pollRef.current = setInterval(tick, options.intervalMs ?? DEFAULT_INTERVAL_MS)
    },
    [stopPoll],
  )

  useEffect(() => () => stopPoll(), [stopPoll])

  return { task, polling, startPoll, stopPoll }
}
