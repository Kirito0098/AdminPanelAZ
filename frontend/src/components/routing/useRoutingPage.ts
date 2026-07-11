import { useCallback, useEffect, useRef, useState } from 'react'
import {
  applyRouting,
  deployCidrToNode,
  generateCidrFromDb,
  getAntifilterStatus,
  getCidrDbStatus,
  getCidrDbStatusSummary,
  getRoutingOverview,
  refreshAntifilter,
  refreshCidrDb,
  clearCidrDb,
  syncRoutingProviders,
  toggleRoutingProvider,
  previewCidrDeploy,
  rollbackCidrFromBackup,
  addCustomCidrProviderEntries,
  ApiError,
} from '@/api/client'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { usePipelineTaskPoll } from '@/components/routing/usePipelineTaskPoll'
import type {
  AntifilterStatus,
  CidrDbStatus,
  CidrDeployPreview,
  CidrPipelineTask,
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
  | 'rollback-cidr'
  | 'sync-providers'
  | null

export function useRoutingPage() {
  const { activeNode, activeNodeHa } = useNode()
  const haReplicaReadonly = activeNodeHa?.role === 'replica'
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
    syncPipelineTask,
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

  const [filterAntifilter, setFilterAntifilter] = useState(false)
  const [deployAllOnline, setDeployAllOnline] = useState(false)
  const [deployTargetNodeIds, setDeployTargetNodeIds] = useState<number[]>([])
  const [selectedProviderFiles, setSelectedProviderFiles] = useState<string[] | null>(null)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)
  const [deployPreview, setDeployPreview] = useState<CidrDeployPreview | null>(null)
  const [deployPreviewLoading, setDeployPreviewLoading] = useState(false)
  const [rollbackStamp, setRollbackStamp] = useState<string | null>(null)
  const [recentRollbackStamp, setRecentRollbackStamp] = useState<string | null>(null)
  const pendingRollbackStampRef = useRef<string | null>(null)
  const [customWizardOpen, setCustomWizardOpen] = useState(false)
  const [customWizardLoading, setCustomWizardLoading] = useState(false)
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
        onComplete: (task) => {
          trackedTaskIdRef.current = null
          setPendingPipelineAction(null)
          success(okMsg)
          if (task.task_type === 'cidr_rollback') {
            const stamp =
              (typeof task.result?.backup_stamp === 'string' && task.result.backup_stamp) ||
              pendingRollbackStampRef.current
            if (stamp) setRecentRollbackStamp(stamp)
            pendingRollbackStampRef.current = null
          }
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
      attachPipelineTask(activeTask.task_id, stage, 'Операция обновления списков завершена', {
        initialTask: activeTask,
        ingestKind,
      })
    },
    [attachPipelineTask],
  )

  const loadPipelineMeta = useCallback(async (opts: { light?: boolean } = {}) => {
    try {
      if (opts.light) {
        const summary = await getCidrDbStatusSummary()
        setCidrDb((prev) =>
          prev
            ? { ...prev, total_cidrs: summary.total_cidrs ?? prev.total_cidrs }
            : prev,
        )
        if (summary.active_task) {
          const active = summary.active_task
          if (trackedTaskIdRef.current !== active.task_id || !pipelinePollingRef.current) {
            resumeActivePipelineTask(active)
          } else {
            syncPipelineTask(active)
          }
        }
        return
      }
      const [dbStatus, afStatus] = await Promise.all([getCidrDbStatus(), getAntifilterStatus()])
      setCidrDb(dbStatus)
      setAntifilter(afStatus)
      if (dbStatus.active_task) {
        const active = dbStatus.active_task
        if (trackedTaskIdRef.current !== active.task_id || !pipelinePollingRef.current) {
          resumeActivePipelineTask(active)
        } else {
          syncPipelineTask(active)
        }
      }
    } catch {
      /* optional panel */
    }
  }, [resumeActivePipelineTask, syncPipelineTask])

  useEffect(() => {
    if (!pipelinePolling) return
    const timer = window.setInterval(() => {
      void loadPipelineMetaRef.current({ light: true })
    }, 10000)
    return () => window.clearInterval(timer)
  }, [pipelinePolling])

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
        await loadPipelineMeta()
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
    [startGlobal, doneGlobal, notifyLoadError, loadPipelineMeta, success],
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
    if (!data?.providers?.length || selectedProviderFiles !== null) return
    setSelectedProviderFiles(data.providers.map((provider) => provider.filename))
  }, [data?.providers, selectedProviderFiles])

  const resolveSelectedProviderPayload = useCallback(
    (files: string[] | null | undefined): string[] | null | undefined => {
      const allCount = data?.providers.length ?? 0
      const targets = files ?? selectedProviderFiles ?? []
      if (targets.length === 0) {
        notifyError('Выберите хотя бы одного провайдера')
        return undefined
      }
      if (allCount > 0 && targets.length >= allCount) {
        return null
      }
      return targets
    },
    [data?.providers.length, notifyError, selectedProviderFiles],
  )

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
    if (haReplicaReadonly) {
      notifyError('HA replica: изменения маршрутизации только на primary')
      return
    }
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

  const runRefreshCidrDb = async (
    files?: string[],
    opts?: { retryFailedMode?: 'last' | 'selected' },
  ) => {
    const payload = resolveSelectedProviderPayload(files)
    if (payload === undefined) return
    const count = files?.length ?? selectedProviderFiles?.length ?? 0
    const okMsg =
      count === 1
        ? 'CIDR провайдера обновлён из интернета'
        : count > 0 && count < (data?.providers.length ?? count)
          ? `CIDR БД обновлена (${count} провайдеров)`
          : 'CIDR БД обновлена из интернета'
    await withPipelineAction(
      () =>
        refreshCidrDb({
          selectedFiles: payload,
          retryFailedMode: opts?.retryFailedMode,
        }),
      okMsg,
      1,
      'providers',
    )
  }

  const refreshOneProvider = async (filename: string) => {
    setSelectedProviderFiles((prev) => [...new Set([...prev, filename])])
    await runRefreshCidrDb([filename])
  }

  const retryFailedProviders = async () => {
    await runRefreshCidrDb(undefined, { retryFailedMode: 'last' })
  }

  const withAction = async (
    fn: () => Promise<unknown>,
    okMsg: string,
    progressLabel = 'Выполнение операции...',
  ) => {
    if (haReplicaReadonly) {
      notifyError('HA replica: изменения маршрутизации только на primary')
      return
    }
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
    if (haReplicaReadonly) {
      notifyError('HA replica: изменения маршрутизации только на primary')
      return
    }
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
        await withBackgroundTask(applyRouting, 'doall + client.sh 7 выполнены')
        break
      case 'sync-providers':
        await withAction(syncRoutingProviders, 'Синхронизация выполнена', 'Синхронизация провайдеров...')
        break
      case 'generate-only': {
        const regions = resolveSelectedProviderPayload()
        if (regions === undefined) return
        const count = selectedProviderFiles?.length ?? 0
        await withPipelineAction(
          () =>
            generateCidrFromDb({
              regions,
              filter_by_antifilter: filterAntifilter,
              deploy_after: false,
              sync_after: false,
              apply_after: false,
            }),
          count > 0 && count < (data?.providers.length ?? count)
            ? `CIDR-файлы собраны (${count} провайдеров)`
            : 'CIDR-файлы собраны на контроллере',
          2,
        )
        break
      }
      case 'generate-doall': {
        const regions = resolveSelectedProviderPayload()
        if (regions === undefined) return
        await withPipelineAction(
          () =>
            generateCidrFromDb({
              regions,
              filter_by_antifilter: filterAntifilter,
              deploy_after: true,
              sync_after: true,
              apply_after: true,
            }),
          'Сгенерировано, развёрнуто и применено (doall.sh)',
          2,
        )
        break
      }
      case 'deploy-only': {
        const selected_files = resolveSelectedProviderPayload()
        if (selected_files === undefined) return
        await withPipelineAction(
          () =>
            deployCidrToNode({
              all_online: deployAllOnline,
              target_node_ids: deployAllOnline ? null : deployTargetNodeIds.length ? deployTargetNodeIds : null,
              sync_after: true,
              apply_after: false,
              recreate_profiles_after: false,
              selected_files,
            }),
          deployAllOnline
            ? 'CIDR-файлы развёрнуты на все узлы в сети'
            : 'CIDR-файлы развёрнуты на выбранные узлы',
          3,
        )
        setDeployPreview(null)
        break
      }
      case 'rollback-cidr': {
        if (!rollbackStamp) {
          notifyError('Выберите резервную копию для отката')
          return
        }
        const selected_files = resolveSelectedProviderPayload()
        if (selected_files === undefined) return
        await withPipelineAction(
          () =>
            rollbackCidrFromBackup({
              backup_stamp: rollbackStamp,
              selected_files,
              redeploy_after: true,
              all_online: deployAllOnline,
              target_node_ids: deployAllOnline ? null : deployTargetNodeIds.length ? deployTargetNodeIds : null,
              sync_after: true,
              apply_after: false,
            }),
          'Откат CIDR из runtime_backups выполнен',
          2,
        )
        setRollbackStamp(null)
        break
      }
    }
  }

  const pipelineBusy =
    actionLoading ||
    pendingPipelineAction != null ||
    (!!pipelineTask && ['queued', 'running'].includes(pipelineTask.status))

  const clearCidrDbData = async () => {
    const selected_files = resolveSelectedProviderPayload()
    if (selected_files === undefined) return
    setActionLoading(true)
    try {
      const result = await clearCidrDb(selected_files)
      success(result.message || 'Данные CIDR БД очищены')
      await load()
    } catch (err) {
      notifyError(errorMessage(err, 'Ошибка очистки CIDR БД'))
    } finally {
      setActionLoading(false)
    }
  }

  const loadDeployPreview = async () => {
    const selected_files = resolveSelectedProviderPayload()
    if (selected_files === undefined) return
    setDeployPreviewLoading(true)
    try {
      const preview = await previewCidrDeploy({
        all_online: deployAllOnline,
        target_node_ids: deployAllOnline ? null : deployTargetNodeIds.length ? deployTargetNodeIds : null,
        selected_files,
      })
      setDeployPreview(preview)
      if (!preview.success && preview.message) {
        notifyError(preview.message)
      }
    } catch (err) {
      notifyError(errorMessage(err, 'Ошибка предпросмотра развёртывания'))
    } finally {
      setDeployPreviewLoading(false)
    }
  }

  const submitCustomProvider = async (payload: {
    providerKey: string
    cidrs_text: string
    asns_text: string
  }) => {
    setCustomWizardLoading(true)
    try {
      const asns = payload.asns_text
        .split(/[\n,;\s]+/)
        .map((line) => line.trim())
        .filter(Boolean)
      const result = await addCustomCidrProviderEntries(payload.providerKey, {
        cidrs_text: payload.cidrs_text,
        asns: asns.length ? asns : undefined,
      })
      success(result.message || 'Записи добавлены в CIDR БД')
      setCustomWizardOpen(false)
      await load()
    } catch (err) {
      notifyError(errorMessage(err, 'Ошибка добавления ASN/CIDR'))
    } finally {
      setCustomWizardLoading(false)
    }
  }

  const requestRollback = (stamp: string) => {
    pendingRollbackStampRef.current = stamp
    setRollbackStamp(stamp)
    setConfirmAction('rollback-cidr')
  }

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
    filterAntifilter,
    setFilterAntifilter,
    deployAllOnline,
    setDeployAllOnline,
    deployTargetNodeIds,
    setDeployTargetNodeIds,
    selectedProviderFiles: selectedProviderFiles ?? [],
    setSelectedProviderFiles,
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
    inline,
    refreshCidrDb: () => runRefreshCidrDb(),
    refreshOneProvider,
    retryFailedProviders,
    refreshAntifilter: () => withPipelineAction(refreshAntifilter, 'Antifilter синхронизирован', 1, 'antifilter'),
    deployCidr: () => setConfirmAction('deploy-only'),
    applyRouting: () => setConfirmAction('apply-doall'),
    loadDeployPreview,
    deployPreview,
    deployPreviewLoading,
    requestRollback,
    rollbackStamp,
    recentRollbackStamp,
    customWizardOpen,
    setCustomWizardOpen,
    customWizardLoading,
    submitCustomProvider,
    clearCidrDbData,
  }
}
