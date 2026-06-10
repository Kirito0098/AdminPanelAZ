import { useCallback, useEffect, useRef, useState } from 'react'
import {
  applyRouting,
  deployCidrToNode,
  generateCidrFromDb,
  getAntifilterStatus,
  getCidrDbStatus,
  getGameFilters,
  getRoutingOverview,
  refreshAntifilter,
  refreshCidrDb,
  syncGameFilters,
  syncRoutingProviders,
  toggleRoutingProvider,
  ApiError,
} from '@/api/client'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { usePipelineTaskPoll } from '@/components/routing/usePipelineTaskPoll'
import type {
  AntifilterStatus,
  CidrDbPresetInfo,
  CidrDbStatus,
  CidrPipelineTask,
  GameFilterItem,
  RoutingOverview,
} from '@/types'
import type { PipelinePendingAction, PipelineStage, IngestKind } from '@/components/routing/utils'
import { getIngestKind, getPipelineStage, isPipelineRunning } from '@/components/routing/utils'

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
  const {
    startGlobal,
    doneGlobal,
    inline,
    withInline,
    trackBackgroundTask,
  } = useProgress()
  const {
    pipelineTask,
    pipelinePolling,
    startPipelinePoll,
  } = usePipelineTaskPoll()

  const [data, setData] = useState<RoutingOverview | null>(null)
  const [cidrDb, setCidrDb] = useState<CidrDbStatus | null>(null)
  const [antifilter, setAntifilter] = useState<AntifilterStatus | null>(null)
  const [pendingPipelineAction, setPendingPipelineAction] = useState<PipelinePendingAction | null>(null)

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
  const trackedTaskIdRef = useRef<string | null>(null)
  const pipelinePollingRef = useRef(false)
  const loadRef = useRef<(opts?: { initial?: boolean; manual?: boolean }) => Promise<void>>(async () => {})
  const loadPipelineMetaRef = useRef<() => Promise<void>>(async () => {})
  const rateLimitNotifiedRef = useRef(false)

  useEffect(() => {
    pipelinePollingRef.current = pipelinePolling
  }, [pipelinePolling])

  const notifyLoadError = useCallback(
    (err: unknown, fallback: string) => {
      if (err instanceof ApiError && err.status === 429) {
        if (!rateLimitNotifiedRef.current) {
          rateLimitNotifiedRef.current = true
          notifyError('Слишком много запросов. Подождите минуту и обновите страницу.')
        }
        return
      }
      notifyError(errorMessage(err, fallback))
    },
    [notifyError],
  )

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
        onComplete: () => {
          trackedTaskIdRef.current = null
          setPendingPipelineAction(null)
          success(okMsg)
          void loadRef.current()
        },
        onError: (task, message) => {
          trackedTaskIdRef.current = null
          setPendingPipelineAction(null)
          if (!message.includes('Слишком много запросов')) {
            notifyError(task?.error || task?.message || message)
          }
          void loadPipelineMetaRef.current()
        },
      })
    },
    [startPipelinePoll, success, notifyError],
  )

  const resumeActivePipelineTask = useCallback(
    (activeTask: NonNullable<CidrDbStatus['active_task']>) => {
      if (!isPipelineRunning(activeTask)) return
      const stage = getPipelineStage(activeTask.task_type) ?? 1
      const ingestKind = getIngestKind(activeTask.task_type) ?? undefined
      attachPipelineTask(activeTask.task_id, stage, 'Операция pipeline завершена', {
        initialTask: activeTask,
        ingestKind,
      })
    },
    [attachPipelineTask],
  )

  const loadPipelineMeta = useCallback(async () => {
    try {
      const [dbStatus, afStatus] = await Promise.all([getCidrDbStatus(), getAntifilterStatus()])
      setCidrDb(dbStatus)
      setAntifilter(afStatus)
      if (dbStatus.active_task) {
        const active = dbStatus.active_task
        if (trackedTaskIdRef.current !== active.task_id || !pipelinePollingRef.current) {
          resumeActivePipelineTask(active)
        }
      }
    } catch {
      /* optional panel */
    }
  }, [resumeActivePipelineTask])

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
        notifyLoadError(err, 'Ошибка загрузки маршрутизации')
      } finally {
        setLoading(false)
        setRefreshing(false)
        if (initial) doneGlobal()
      }
    },
    [startGlobal, doneGlobal, notifyLoadError, loadPipelineMeta, loadGames, success],
  )

  useEffect(() => {
    loadRef.current = load
    loadPipelineMetaRef.current = loadPipelineMeta
  }, [load, loadPipelineMeta])

  useEffect(() => {
    if (activeNode?.id && deployTargetNodeIds.length === 0) {
      setDeployTargetNodeIds([activeNode.id])
    }
  }, [activeNode?.id, deployTargetNodeIds.length])

  useEffect(() => {
    void load({ initial: true })
    // Reload only when active node changes, not when load callback identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeNode?.id])

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
    stage: PipelineStage,
    ingestKind?: IngestKind,
  ) => {
    setActionLoading(true)
    try {
      const resp = await fn()
      attachPipelineTask(resp.task_id, stage, okMsg, { force: true, ingestKind })
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
          2,
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
          2,
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
          3,
        )
        break
    }
  }

  const pipelineBusy =
    actionLoading ||
    pendingPipelineAction != null ||
    (!!pipelineTask && ['queued', 'running'].includes(pipelineTask.status))

  return {
    data,
    cidrDb,
    antifilter,
    pipelineTask,
    pendingPipelineAction,
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
    refreshCidrDb: () => withPipelineAction(refreshCidrDb, 'CIDR БД обновлена из интернета', 1, 'providers'),
    refreshAntifilter: () => withPipelineAction(refreshAntifilter, 'Antifilter синхронизирован', 1, 'antifilter'),
    deployCidr: () => setConfirmAction('deploy-only'),
  }
}
