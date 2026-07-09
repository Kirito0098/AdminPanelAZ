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
  formatPollError?: (message: string) => string
  /** Не показывать нижнюю полосу прогресса (тихий опрос). */
  showProgress?: boolean
  /** Временные сбои опроса (502 при перезапуске) — не считать ошибкой. */
  isTransientPollError?: (err: unknown, message: string) => boolean
  transientProgressStage?: string
  initialTask?: BackgroundTask
  onProgress?: (task: BackgroundTask) => void
  onComplete?: (task: BackgroundTask) => void
  onError?: (task: BackgroundTask | null, message: string) => void
}

export function useBackgroundTaskPoll() {
  const [task, setTask] = useState<BackgroundTask | null>(null)
  const [polling, setPolling] = useState(false)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pollActiveRef = useRef(false)
  const inFlightRef = useRef(false)
  const startedAtRef = useRef<number>(0)
  const errorCountRef = useRef(0)
  const optionsRef = useRef<BackgroundTaskPollOptions>({})
  const taskRef = useRef<BackgroundTask | null>(null)
  const pollOnceRef = useRef<(taskId: string) => Promise<boolean>>(async () => false)
  const errorNotifiedRef = useRef(false)

  const stopPoll = useCallback(() => {
    pollActiveRef.current = false
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
    setPolling(false)
  }, [])

  const pollOnce = useCallback(async (taskId: string): Promise<boolean> => {
    const opts = optionsRef.current
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS
    if (Date.now() - startedAtRef.current > timeoutMs) {
      stopPoll()
      opts.onError?.(taskRef.current, 'Превышено время ожидания задачи')
      return false
    }

    try {
      const fetchTask = opts.fetchTask ?? getBackgroundTask
      const current = await fetchTask(taskId)
      if (!current?.task_id) {
        throw new ApiError('Некорректный ответ сервера о статусе задачи', 500)
      }
      errorCountRef.current = 0
      taskRef.current = current
      if (opts.showProgress !== false) {
        setTask(current)
      }
      opts.onProgress?.(current)
      if (current.status === 'completed') {
        stopPoll()
        opts.onComplete?.(current)
        return false
      }
      if (current.status === 'failed') {
        stopPoll()
        opts.onError?.(current, current.error || current.message || 'Задача завершилась с ошибкой')
        return false
      }
      return true
    } catch (err) {
      const isRateLimit = err instanceof ApiError && err.status === 429
      const rawMessage = err instanceof ApiError ? err.message : 'Ошибка отслеживания задачи'
      const message = opts.formatPollError?.(rawMessage) ?? rawMessage
      const isTransient = opts.isTransientPollError?.(err, message) ?? false

      if (isTransient) {
        if (opts.showProgress !== false) {
          setTask((prev) =>
            prev
              ? {
                  ...prev,
                  progress_stage:
                    opts.transientProgressStage ??
                    'Сервис перезапускается. Подождите и откройте новый адрес панели…',
                  message: opts.transientProgressStage ?? 'Сервис перезапускается…',
                }
              : prev,
          )
        }
        return true
      }

      if (opts.showProgress !== false) {
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
      }
      if (isRateLimit) {
        return true
      }
      errorCountRef.current += 1
      if (errorCountRef.current >= MAX_CONSECUTIVE_ERRORS) {
        stopPoll()
        if (!errorNotifiedRef.current) {
          errorNotifiedRef.current = true
          opts.onError?.(taskRef.current, message)
        }
        return false
      }
      return true
    }
  }, [stopPoll])

  pollOnceRef.current = pollOnce

  const scheduleNextPoll = useCallback((taskId: string) => {
    if (!pollActiveRef.current) return
    const intervalMs = optionsRef.current.intervalMs ?? DEFAULT_INTERVAL_MS
    pollTimerRef.current = setTimeout(() => {
      if (!pollActiveRef.current || inFlightRef.current) {
        scheduleNextPoll(taskId)
        return
      }
      inFlightRef.current = true
      void pollOnceRef
        .current(taskId)
        .then((shouldContinue) => {
          if (shouldContinue && pollActiveRef.current) {
            scheduleNextPoll(taskId)
          }
        })
        .finally(() => {
          inFlightRef.current = false
        })
    }, intervalMs)
  }, [])

  const startPoll = useCallback(
    (taskId: string, options: BackgroundTaskPollOptions = {}) => {
      stopPoll()
      optionsRef.current = options
      startedAtRef.current = Date.now()
      errorCountRef.current = 0
      errorNotifiedRef.current = false
      pollActiveRef.current = true
      setPolling(true)
      if (options.showProgress !== false) {
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
      } else {
        setTask(null)
      }

      inFlightRef.current = true
      void pollOnceRef
        .current(taskId)
        .then((shouldContinue) => {
          if (shouldContinue && pollActiveRef.current) {
            scheduleNextPoll(taskId)
          }
        })
        .finally(() => {
          inFlightRef.current = false
        })
    },
    [stopPoll, scheduleNextPoll],
  )

  useEffect(() => () => stopPoll(), [stopPoll])

  const syncTask = useCallback((next: BackgroundTask) => {
    if (!next?.task_id) return
    taskRef.current = next
    setTask(next)
  }, [])

  return { task, polling, startPoll, stopPoll, syncTask }
}
