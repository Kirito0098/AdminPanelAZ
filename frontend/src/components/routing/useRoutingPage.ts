import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  applyRouting,
  applyRoutingPreset,
  generateCidrFromDb,
  getAntifilterStatus,
  getCidrDbStatus,
  getCidrPipelineTask,
  getGameFilters,
  getRoutingOverview,
  refreshAntifilter,
  refreshCidrDb,
  syncGameFilters,
  syncRoutingProviders,
  toggleRoutingProvider,
} from '@/api/client'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import type { AntifilterStatus, CidrDbStatus, CidrPipelineTask, GameFilterItem, RoutingOverview } from '@/types'

export const REFRESH_INTERVAL = 60

export type ConfirmAction =
  | 'apply-doall'
  | 'generate-doall'
  | 'generate-only'
  | 'sync-providers'
  | null

export function useRoutingPage() {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal, inline, withInline, trackBackgroundTask } = useProgress()

  const [data, setData] = useState<RoutingOverview | null>(null)
  const [cidrDb, setCidrDb] = useState<CidrDbStatus | null>(null)
  const [antifilter, setAntifilter] = useState<AntifilterStatus | null>(null)
  const [pipelineTask, setPipelineTask] = useState<CidrPipelineTask | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)

  const [games, setGames] = useState<GameFilterItem[]>([])
  const [gameModes, setGameModes] = useState<Record<string, string>>({})
  const [filterAntifilter, setFilterAntifilter] = useState(false)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)

  const loadPipelineMeta = useCallback(async () => {
    try {
      const [dbStatus, afStatus] = await Promise.all([getCidrDbStatus(), getAntifilterStatus()])
      setCidrDb(dbStatus)
      setAntifilter(afStatus)
    } catch {
      /* optional panel */
    }
  }, [])

  const loadGames = useCallback(async () => {
    try {
      const { games: gameList } = await getGameFilters()
      setGames(gameList)
      const modes: Record<string, string> = {}
      gameList.forEach((g) => {
        modes[g.key] = g.mode
      })
      setGameModes(modes)
    } catch {
      /* optional panel */
    }
  }, [])

  const load = useCallback(
    async (opts: { initial?: boolean; manual?: boolean } = {}) => {
      const { initial = false, manual = false } = opts
      if (initial) {
        setLoading(true)
        startGlobal()
      } else if (manual) {
        setRefreshing(true)
      }
      try {
        setData(await getRoutingOverview())
        await Promise.all([loadPipelineMeta(), loadGames()])
        setCountdown(REFRESH_INTERVAL)
        if (manual) success('Данные маршрутизации обновлены')
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки маршрутизации')
      } finally {
        setLoading(false)
        setRefreshing(false)
        if (initial) doneGlobal()
      }
    },
    [startGlobal, doneGlobal, notifyError, loadPipelineMeta, loadGames, success],
  )

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const pollTask = useCallback(
    (taskId: string, okMsg: string) => {
      stopPolling()
      pollRef.current = setInterval(async () => {
        try {
          const { task } = await getCidrPipelineTask(taskId)
          setPipelineTask(task)
          if (task.status === 'completed') {
            stopPolling()
            success(okMsg)
            await load()
          } else if (task.status === 'failed') {
            stopPolling()
            notifyError(task.error || task.message || 'Ошибка pipeline')
            await loadPipelineMeta()
          }
        } catch (err) {
          stopPolling()
          notifyError(err instanceof ApiError ? err.message : 'Ошибка отслеживания задачи')
        }
      }, 1500)
    },
    [load, loadPipelineMeta, notifyError, stopPolling, success],
  )

  useEffect(() => () => stopPolling(), [stopPolling])

  useEffect(() => {
    load({ initial: true })
  }, [load, activeNode?.id])

  useEffect(() => {
    if (!autoRefresh) return
    const tick = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          load()
          return REFRESH_INTERVAL
        }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(tick)
  }, [autoRefresh, load])

  const withPipelineAction = async (
    fn: () => Promise<{ task_id: string; message: string }>,
    okMsg: string,
  ) => {
    setActionLoading(true)
    try {
      const resp = await fn()
      setPipelineTask({
        task_id: resp.task_id,
        task_type: '',
        status: 'queued',
        message: resp.message,
        progress_percent: 0,
        progress_stage: resp.message,
      })
      pollTask(resp.task_id, okMsg)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка операции')
    } finally {
      setActionLoading(false)
    }
  }

  const withAction = async (
    fn: () => Promise<unknown>,
    okMsg: string,
    progressLabel = 'Выполнение операции...',
  ) => {
    setActionLoading(true)
    try {
      await withInline(fn, progressLabel)
      success(okMsg)
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка операции')
    } finally {
      setActionLoading(false)
    }
  }

  const withBackgroundTask = async (
    fn: () => Promise<{ task_id: string; message?: string }>,
    okMsg: string,
  ) => {
    setActionLoading(true)
    try {
      const resp = await fn()
      trackBackgroundTask(resp.task_id, {
        onComplete: () => {
          success(okMsg)
          void load()
        },
        onError: (task, message) => {
          notifyError(task?.error || task?.message || message)
        },
      })
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка операции')
    } finally {
      setActionLoading(false)
    }
  }

  const executeConfirm = async () => {
    const action = confirmAction
    setConfirmAction(null)
    if (!action) return

    switch (action) {
      case 'apply-doall':
        await withBackgroundTask(applyRouting, 'doall.sh выполнен')
        break
      case 'sync-providers':
        await withAction(syncRoutingProviders, 'Синхронизация выполнена', 'Синхронизация провайдеров...')
        break
      case 'generate-only':
        await withPipelineAction(
          () => generateCidrFromDb({ filter_by_antifilter: filterAntifilter, apply_after: false }),
          'CIDR-файлы сгенерированы из БД',
        )
        break
      case 'generate-doall':
        await withPipelineAction(
          () => generateCidrFromDb({ filter_by_antifilter: filterAntifilter, apply_after: true }),
          'Сгенерировано и применено (doall.sh)',
        )
        break
    }
  }

  const pipelineBusy = actionLoading || (!!pipelineTask && ['queued', 'running'].includes(pipelineTask.status))

  return {
    data,
    cidrDb,
    antifilter,
    pipelineTask,
    loading,
    refreshing,
    actionLoading,
    pipelineBusy,
    autoRefresh,
    setAutoRefresh,
    countdown,
    games,
    gameModes,
    setGameModes,
    filterAntifilter,
    setFilterAntifilter,
    confirmAction,
    setConfirmAction,
    load,
    withPipelineAction,
    withAction,
    executeConfirm,
    toggleProvider: (filename: string, enabled: boolean, name: string) =>
      withAction(
        () => toggleRoutingProvider(filename, enabled),
        enabled ? `${name} включён` : `${name} отключён`,
        enabled ? `Включение ${name}...` : `Отключение ${name}...`,
      ),
    applyPreset: (key: string, name: string) =>
      withAction(() => applyRoutingPreset(key), `Пресет «${name}» применён`, `Применение пресета «${name}»...`),
    syncGames: () =>
      withAction(() => syncGameFilters(gameModes), 'Игровые фильтры синхронизированы', 'Синхронизация игровых фильтров...'),
    inline,
    refreshCidrDb: () => withPipelineAction(refreshCidrDb, 'CIDR БД обновлена из интернета'),
    refreshAntifilter: () => withPipelineAction(refreshAntifilter, 'Antifilter синхронизирован'),
  }
}
