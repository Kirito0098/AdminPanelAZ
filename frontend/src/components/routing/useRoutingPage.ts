import { useCallback, useEffect, useRef, useState } from 'react'
import {
  applyRouting,
  deployCidrToNode,
  estimateCidrFromDb,
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
} from '@/api/client'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useIntervalWhenVisible } from '@/hooks/useIntervalWhenVisible'
import { createLatestRequest } from '@/lib/latestRequest'
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
  | 'generate-only'
  | 'rollback-cidr'
  | 'sync-providers'
  | null

export function useRoutingPage() {
  const { activeNode, activeNodeHa, loading: nodeLoading } = useNode()
  const haReplicaReadonly = activeNodeHa?.role === 'replica'
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
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
  // Only the deadline lives in the hook: the ticking seconds are rendered by RoutingPageHeader,
  // so a 1 Hz counter no longer re-renders the whole page tree.
  const [nextRefreshAt, setNextRefreshAt] = useState<number | null>(null)

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
  /** Растёт после каждой завершённой задачи пайплайна: по нему UI перезапрашивает бюджет маршрутов. */
  const [lastTaskFinishedAt, setLastTaskFinishedAt] = useState(0)
  const trackedTaskIdRef = useRef<string | null>(null)
  const pipelinePollingRef = useRef(false)
  const loadRef = useRef<(opts?: { initial?: boolean; manual?: boolean; fullMeta?: boolean }) => Promise<void>>(
    async () => {},
  )
  const loadPipelineMetaRef = useRef<(opts?: { light?: boolean }) => Promise<void>>(async () => {})
  // Answers only apply to the node they were requested for, and only while no newer request is out.
  const [latestNodeRequest] = useState(() => createLatestRequest<number | null>(null))
  const inFlightRef = useRef<{ scope: number | null; full: boolean; promise: Promise<void> } | null>(null)
  const refreshDueRef = useRef(false)

  useEffect(() => {
    pipelinePollingRef.current = pipelinePolling
  }, [pipelinePolling])

  // Single HA gate for every routing mutation (pipeline, inline, background, clear, custom provider).
  const guardMutation = useCallback((): boolean => {
    if (!haReplicaReadonly) return false
    notifyError('HA replica: изменения маршрутизации только на primary')
    return true
  }, [haReplicaReadonly, notifyError])

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

  const loadPipelineMeta = useCallback(async (opts: { light?: boolean; guard?: () => boolean } = {}) => {
    const guard = opts.guard
    const stale = () => guard !== undefined && !guard()
    try {
      if (opts.light) {
        const summary = await getCidrDbStatusSummary()
        if (stale()) return
        setCidrDb((prev) =>
          prev
            ? {
                ...prev,
                total_cidrs: summary.total_cidrs ?? prev.total_cidrs,
                active_task: summary.active_task ?? prev.active_task,
              }
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
      if (stale()) return
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

  // Pipeline progress comes from usePipelineTaskPoll (5s). Do not dual-poll
  // /cidr-db/status/summary every 10s while a task is already tracked.

  const startLoad = useCallback(
    (opts: { initial?: boolean; manual?: boolean; fullMeta?: boolean; scope: number | null }): Promise<void> => {
      const { initial = false, manual = false, fullMeta = false, scope } = opts
      const isCurrent = latestNodeRequest.begin(scope)
      // The shown node is gone (or a newer request took over) — do not even fire the request.
      if (!isCurrent()) return Promise.resolve()
      // Auto-refresh: light CIDR meta only (summary). Full ASN/artifacts status
      // on initial load, manual refresh, and after pipeline completion.
      const wantFullMeta = fullMeta || initial || manual

      if (initial) {
        setLoading(true)
        startGlobal()
      } else if (manual) {
        setRefreshing(true)
      }

      let tracked: Promise<void> | null = null
      const run = async () => {
        try {
          const [overview] = await Promise.all([
            getRoutingOverview(),
            loadPipelineMeta({ ...(wantFullMeta ? {} : { light: true }), guard: isCurrent }),
          ])
          if (!isCurrent()) return
          setData(overview)
          if (manual) success('Данные маршрутизации обновлены')
        } catch (err) {
          if (isCurrent()) notifyError(errorMessage(err, 'Ошибка загрузки маршрутизации'))
        } finally {
          if (inFlightRef.current?.promise === tracked) inFlightRef.current = null
          if (isCurrent()) {
            // Re-arm the deadline on failure too: a broken request must not retry every tick.
            setNextRefreshAt(Date.now() + REFRESH_INTERVAL * 1000)
            setLoading(false)
            setRefreshing(false)
            if (initial) doneGlobal()
          }
        }
      }
      tracked = run()
      inFlightRef.current = { scope, full: wantFullMeta, promise: tracked }
      return tracked
    },
    [startGlobal, doneGlobal, loadPipelineMeta, success, latestNodeRequest],
  )

  const load = useCallback(
    (opts: { initial?: boolean; manual?: boolean; fullMeta?: boolean } = {}): Promise<void> => {
      const { initial = false, manual = false, fullMeta = false } = opts
      const scope = activeNode?.id ?? null
      const wantFullMeta = fullMeta || initial || manual
      const running = inFlightRef.current
      // Auto-refresh and manual refresh must not hit the endpoint twice. A heavier request
      // (manual/full meta) waits for the light one instead of being swallowed by it.
      if (running && running.scope === scope) {
        if (!wantFullMeta || running.full) return running.promise
        return running.promise.then(() => startLoad({ initial, manual, fullMeta, scope }))
      }
      return startLoad({ initial, manual, fullMeta, scope })
    },
    [activeNode?.id, startLoad],
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
    (files?: string[] | null): string[] | null | undefined => {
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
    // The shown node changed (or the node list was reloaded): answers of requests started
    // before it no longer describe the page, so drop them and start a request for the new node.
    latestNodeRequest.reset(activeNode?.id ?? null)
    inFlightRef.current = null
    if (nodeLoading) return
    void load({ initial: true })
    // Reload only when active node changes, not when load callback identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeLoading, activeNode?.id, latestNodeRequest])

  // Enabling auto-refresh arms the first deadline; later loads re-arm it themselves.
  useEffect(() => {
    if (!autoRefresh) return
    setNextRefreshAt((prev) =>
      prev !== null && prev > Date.now() ? prev : Date.now() + REFRESH_INTERVAL * 1000,
    )
  }, [autoRefresh])

  useIntervalWhenVisible(
    () => {
      if (nextRefreshAt === null || Date.now() < nextRefreshAt) return
      if (refreshDueRef.current) return
      refreshDueRef.current = true
      void load().finally(() => {
        refreshDueRef.current = false
      })
    },
    1000,
    {
      enabled: autoRefresh,
      onBecomeVisible: () => {
        void load()
      },
    },
  )

  // A deploy preview describes exactly the targets it was built for: a changed selection
  // must fetch a new one instead of confirming someone else's diff.
  useEffect(() => {
    setDeployPreview(null)
  }, [deployAllOnline, deployTargetNodeIds, selectedProviderFiles])

  const withPipelineAction = async (
    fn: () => Promise<{ task_id: string; message: string }>,
    okMsg: string,
    stage: PipelineStage,
    ingestKind?: IngestKind,
  ) => {
    if (guardMutation()) return
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
    setSelectedProviderFiles((prev) => [...new Set([...(prev ?? []), filename])])
    await runRefreshCidrDb([filename])
  }

  const retryFailedProviders = async () => {
    await runRefreshCidrDb(undefined, { retryFailedMode: 'last' })
  }

  /** Dry-run: пересчитать бюджет маршрутов по текущей БД, файлы на узлах не меняются. */
  const estimateCidr = async () => {
    const regions = resolveSelectedProviderPayload()
    if (regions === undefined) return
    await withPipelineAction(
      () => estimateCidrFromDb({ regions, filter_by_antifilter: filterAntifilter }),
      'Оценка бюджета маршрутов обновлена',
      2,
    )
  }

  const withAction = async (
    fn: () => Promise<unknown>,
    okMsg: string,
    progressLabel = 'Выполнение операции...',
  ) => {
    if (guardMutation()) return
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
    if (guardMutation()) return
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
        await withBackgroundTask(syncRoutingProviders, 'Синхронизация выполнена')
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
    if (guardMutation()) return
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
    if (guardMutation()) return
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
    nextRefreshAt,
    /** Время последней завершённой задачи пайплайна — триггер перезапроса бюджета маршрутов. */
    lastTaskFinishedAt,
    /** HA replica: routing is read-only on this node, mutating buttons must be disabled. */
    readonly: haReplicaReadonly,
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
        async () => {
          const resp = await toggleRoutingProvider(filename, enabled)
          if (resp.warnings?.length) notifyWarning(resp.warnings.join('; '))
          return resp
        },
        enabled ? `${name} включён` : `${name} отключён`,
        enabled ? `Включение ${name}...` : `Отключение ${name}...`,
      ),
    inline,
    refreshCidrDb: () => runRefreshCidrDb(),
    refreshOneProvider,
    retryFailedProviders,
    estimateCidr,
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
