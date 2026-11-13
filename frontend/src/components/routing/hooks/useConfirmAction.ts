import { useCallback, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import {
  applyRouting,
  deployCidrToNode,
  generateCidrFromDb,
  rollbackCidrFromBackup,
  syncRoutingProviders,
} from '@/api/client'
import { useNotifications } from '@/context/NotificationContext'
import type { CidrDeployPreview } from '@/types'
import type { WithBackgroundTask, WithPipelineAction } from './useCidrPipelineActions'

export type ConfirmAction =
  | 'apply-doall'
  | 'deploy-only'
  | 'generate-only'
  | 'rollback-cidr'
  | 'sync-providers'
  | null

interface Args {
  withPipelineAction: WithPipelineAction
  withBackgroundTask: WithBackgroundTask
  resolveSelectedProviderPayload: (files?: string[] | null) => string[] | null | undefined
  selectedProviderFiles: string[] | null
  providersCount: number
  filterAntifilter: boolean
  deployAllOnline: boolean
  deployTargetNodeIds: number[]
  setDeployPreview: Dispatch<SetStateAction<CidrDeployPreview | null>>
  rollbackStamp: string | null
  setRollbackStamp: Dispatch<SetStateAction<string | null>>
  requestRollbackSelection: (stamp: string) => void
}

/** Destructive routing confirmations: dialog state and the branch that runs the chosen action. */
export function useConfirmAction({
  withPipelineAction,
  withBackgroundTask,
  resolveSelectedProviderPayload,
  selectedProviderFiles,
  providersCount,
  filterAntifilter,
  deployAllOnline,
  deployTargetNodeIds,
  setDeployPreview,
  rollbackStamp,
  setRollbackStamp,
  requestRollbackSelection,
}: Args) {
  const { error: notifyError } = useNotifications()
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)

  const executeConfirm = useCallback(async () => {
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
          count > 0 && count < providersCount
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
  }, [
    confirmAction,
    withBackgroundTask,
    withPipelineAction,
    resolveSelectedProviderPayload,
    selectedProviderFiles,
    providersCount,
    filterAntifilter,
    deployAllOnline,
    deployTargetNodeIds,
    setDeployPreview,
    rollbackStamp,
    setRollbackStamp,
    notifyError,
  ])

  const requestRollback = useCallback(
    (stamp: string) => {
      requestRollbackSelection(stamp)
      setConfirmAction('rollback-cidr')
    },
    [requestRollbackSelection],
  )

  const deployCidr = useCallback(() => setConfirmAction('deploy-only'), [])
  const applyRoutingAction = useCallback(() => setConfirmAction('apply-doall'), [])

  return {
    confirmAction,
    setConfirmAction,
    executeConfirm,
    requestRollback,
    deployCidr,
    applyRouting: applyRoutingAction,
  }
}
