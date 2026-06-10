import { useCallback, useEffect, useRef, useState } from 'react'
import {
  applyRouting,
  deployCidrToNode,
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
import type {
  AntifilterStatus,
  CidrDbPresetInfo,
  CidrDbStatus,
  CidrPipelineTask,
  GameFilterItem,
  RoutingOverview,
} from '@/types'

export const REFRESH_INTERVAL = 60

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message
  return fallback
}

export type ConfirmAction =
  | 'apply-doall'
  | 'deploy-only'
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
  const [deployAllOnline, setDeployAllOnline] = useState(false)
  const [deployTargetNodeIds, setDeployTargetNodeIds] = useState<number[]>([])
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
        notifyError(errorMessage(err, 'Ошибка загрузки маршрутизации'))
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
          notifyError(errorMessage(err, 'Ошибка отслеживания задачи'))
        }
      }, 1500)
    },
    [load, loadPipelineMeta, notifyError, stopPolling, success],
  )

  useEffect(() => () => stopPolling(), [stopPolling])

  useEffect(() => {
    if (activeNode?.id && deployTargetNodeIds.length === 0) {
      setDeployTargetNodeIds([activeNode.id])
    }
  }, [activeNode?.id, deployTargetNodeIds.length])

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
      notifyError(errorMessage(err, 'Ошибка операции'))
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
      notifyError(errorMessage(err, 'Ошибка операции'))
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
      notifyError(errorMessage(err, 'Ошибка операции'))
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
          () =>
            generateCidrFromDb({
              filter_by_antifilter: filterAntifilter,
              deploy_after: false,
              sync_after: false,
              apply_after: false,
            }),
          'CIDR-файлы собраны на контроллере',
        )
        break
      case 'generate-doall':
        await withPipelineAction(
          () =>
            generateCidrFromDb({
              filter_by_antifilter: filterAntifilter,
              deploy_after: true,
              sync_after: true,
              apply_after: true,
            }),
          'Сгенерировано, развёрнуто и применено (doall.sh)',
        )
        break
      case 'deploy-only':
        await withPipelineAction(
          () =>
            deployCidrToNode({
              all_online: deployAllOnline,
              target_node_ids: deployAllOnline ? null : deployTargetNodeIds.length ? deployTargetNodeIds : null,
              sync_after: true,
              apply_after: false,
            }),
          deployAllOnline
            ? 'CIDR-файлы развёрнуты на все online-ноды'
            : 'CIDR-файлы развёрнуты на выбранные ноды',
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
    deployAllOnline,
    setDeployAllOnline,
    deployTargetNodeIds,
    setDeployTargetNodeIds,
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
    applyPreset: (preset: CidrDbPresetInfo) =>
      withAction(async () => {
        if (!data) throw new Error('Нет данных маршрутизации')
        const targetProviders = new Set(preset.providers)
        const toggles = data.providers
          .filter((provider) => provider.enabled !== targetProviders.has(provider.filename))
          .map((provider) => toggleRoutingProvider(provider.filename, targetProviders.has(provider.filename)))
        await Promise.all(toggles)
      }, `Пресет «${preset.name}» применён`, `Применение пресета «${preset.name}»...`),
    syncGames: () =>
      withAction(() => syncGameFilters(gameModes), 'Игровые фильтры синхронизированы', 'Синхронизация игровых фильтров...'),
    inline,
    refreshCidrDb: () => withPipelineAction(refreshCidrDb, 'CIDR БД обновлена из интернета'),
    refreshAntifilter: () => withPipelineAction(refreshAntifilter, 'Antifilter синхронизирован'),
    deployCidr: () => setConfirmAction('deploy-only'),
  }
}
