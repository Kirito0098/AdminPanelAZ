import { useCallback, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import {
  addCustomCidrProviderEntries,
  clearCidrDb,
  estimateCidrFromDb,
  previewCidrDeploy,
  refreshAntifilter,
  refreshCidrDb,
  toggleRoutingProvider,
} from '@/api/client'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import type { CidrDeployPreview, CidrPipelineTask } from '@/types'
import type { IngestKind, PipelinePendingAction, PipelineStage } from '@/components/routing/utils'
import { errorMessage } from './errors'
import type { AttachPipelineTask, LoadRouting } from './types'

export type WithPipelineAction = (
  fn: () => Promise<{ task_id: string; message: string }>,
  okMsg: string,
  stage: PipelineStage,
  ingestKind?: IngestKind,
) => Promise<void>

export type WithBackgroundTask = (
  fn: () => Promise<{ task_id: string; message?: string }>,
  okMsg: string,
) => Promise<void>

interface Args {
  load: LoadRouting
  providersCount: number
  selectedProviderFiles: string[] | null
  setSelectedProviderFiles: Dispatch<SetStateAction<string[] | null>>
  resolveSelectedProviderPayload: (files?: string[] | null) => string[] | null | undefined
  deployAllOnline: boolean
  deployTargetNodeIds: number[]
  setDeployPreview: Dispatch<SetStateAction<CidrDeployPreview | null>>
  setDeployPreviewLoading: Dispatch<SetStateAction<boolean>>
  attachPipelineTask: AttachPipelineTask
  pipelineTask: CidrPipelineTask | null
  pendingPipelineAction: PipelinePendingAction | null
  /** HA replica: every mutation is refused with the same message. */
  readonly: boolean
}

/** Routing mutations: pipeline actions, inline actions, background tasks and the custom provider wizard. */
export function useCidrPipelineActions({
  load,
  providersCount,
  selectedProviderFiles,
  setSelectedProviderFiles,
  resolveSelectedProviderPayload,
  deployAllOnline,
  deployTargetNodeIds,
  setDeployPreview,
  setDeployPreviewLoading,
  attachPipelineTask,
  pipelineTask,
  pendingPipelineAction,
  readonly,
}: Args) {
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
  const { withInline, trackBackgroundTask } = useProgress()

  const [actionLoading, setActionLoading] = useState(false)
  const [filterAntifilter, setFilterAntifilter] = useState(false)
  const [customWizardOpen, setCustomWizardOpen] = useState(false)
  const [customWizardLoading, setCustomWizardLoading] = useState(false)

  // Single HA gate for every routing mutation (pipeline, inline, background, clear, custom provider).
  const guardMutation = useCallback((): boolean => {
    if (!readonly) return false
    notifyError('HA replica: изменения маршрутизации только на primary')
    return true
  }, [readonly, notifyError])

  const withPipelineAction = useCallback<WithPipelineAction>(
    async (fn, okMsg, stage, ingestKind) => {
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
    },
    [guardMutation, attachPipelineTask, notifyError],
  )

  const runRefreshCidrDb = useCallback(
    async (files?: string[], opts?: { retryFailedMode?: 'last' | 'selected' }) => {
      const payload = resolveSelectedProviderPayload(files)
      if (payload === undefined) return
      const count = files?.length ?? selectedProviderFiles?.length ?? 0
      const okMsg =
        count === 1
          ? 'CIDR провайдера обновлён из интернета'
          : count > 0 && count < providersCount
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
    },
    [resolveSelectedProviderPayload, selectedProviderFiles, providersCount, withPipelineAction],
  )

  const refreshOneProvider = useCallback(
    async (filename: string) => {
      setSelectedProviderFiles((prev) => [...new Set([...(prev ?? []), filename])])
      await runRefreshCidrDb([filename])
    },
    [setSelectedProviderFiles, runRefreshCidrDb],
  )

  const retryFailedProviders = useCallback(async () => {
    await runRefreshCidrDb(undefined, { retryFailedMode: 'last' })
  }, [runRefreshCidrDb])

  /** Dry-run: пересчитать бюджет маршрутов по текущей БД, файлы на узлах не меняются. */
  const estimateCidr = useCallback(async () => {
    const regions = resolveSelectedProviderPayload()
    if (regions === undefined) return
    await withPipelineAction(
      () => estimateCidrFromDb({ regions, filter_by_antifilter: filterAntifilter }),
      'Оценка бюджета маршрутов обновлена',
      2,
    )
  }, [resolveSelectedProviderPayload, withPipelineAction, filterAntifilter])

  const withAction = useCallback(
    async (fn: () => Promise<unknown>, okMsg: string, progressLabel = 'Выполнение операции...') => {
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
    },
    [guardMutation, withInline, success, load, notifyError],
  )

  const withBackgroundTask = useCallback<WithBackgroundTask>(
    async (fn, okMsg) => {
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
    },
    [guardMutation, trackBackgroundTask, success, load, notifyError],
  )

  const clearCidrDbData = useCallback(async () => {
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
  }, [guardMutation, resolveSelectedProviderPayload, success, load, notifyError])

  const loadDeployPreview = useCallback(async () => {
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
  }, [
    resolveSelectedProviderPayload,
    deployAllOnline,
    deployTargetNodeIds,
    setDeployPreview,
    setDeployPreviewLoading,
    notifyError,
  ])

  const submitCustomProvider = useCallback(
    async (payload: { providerKey: string; cidrs_text: string; asns_text: string }) => {
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
    },
    [guardMutation, success, load, notifyError],
  )

  const toggleProvider = useCallback(
    (filename: string, enabled: boolean, name: string) =>
      withAction(
        async () => {
          const resp = await toggleRoutingProvider(filename, enabled)
          if (resp.warnings?.length) notifyWarning(resp.warnings.join('; '))
          return resp
        },
        enabled ? `${name} включён` : `${name} отключён`,
        enabled ? `Включение ${name}...` : `Отключение ${name}...`,
      ),
    [withAction, notifyWarning],
  )

  const pipelineBusy =
    actionLoading ||
    pendingPipelineAction != null ||
    (!!pipelineTask && ['queued', 'running'].includes(pipelineTask.status))

  return {
    actionLoading,
    pipelineBusy,
    readonly,
    guardMutation,
    filterAntifilter,
    setFilterAntifilter,
    customWizardOpen,
    setCustomWizardOpen,
    customWizardLoading,
    withPipelineAction,
    withBackgroundTask,
    withAction,
    toggleProvider,
    refreshCidrDb: () => runRefreshCidrDb(),
    refreshOneProvider,
    retryFailedProviders,
    estimateCidr,
    refreshAntifilter: () => withPipelineAction(refreshAntifilter, 'Antifilter синхронизирован', 1, 'antifilter'),
    clearCidrDbData,
    loadDeployPreview,
    submitCustomProvider,
  }
}
