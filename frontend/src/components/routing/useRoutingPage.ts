import { useRef } from 'react'
import { useNode } from '@/context/NodeContext'
import { useProgress } from '@/context/ProgressContext'
import { useRoutingPipelineTask } from './hooks/useRoutingPipelineTask'
import { useRoutingData } from './hooks/useRoutingData'
import { useProviderSelection } from './hooks/useProviderSelection'
import { useDeployTargets } from './hooks/useDeployTargets'
import { useCidrPipelineActions } from './hooks/useCidrPipelineActions'
import { useConfirmAction } from './hooks/useConfirmAction'
import type { LoadRouting, ReloadPipelineMeta } from './hooks/types'

export { REFRESH_INTERVAL } from './hooks/types'
export type { ConfirmAction } from './hooks/useConfirmAction'

/**
 * Routing page state, composed from focused hooks:
 * data → provider selection → deploy targets → actions → confirmations.
 *
 * The loaders are created here as refs because the pipeline tracking hook is declared
 * before them (meta loading resumes an active task) while task callbacks need the loaders.
 */
export function useRoutingPage() {
  const { activeNode, activeNodeHa, loading: nodeLoading } = useNode()
  const readonly = activeNodeHa?.role === 'replica'
  const { inline } = useProgress()

  const loadRef = useRef<LoadRouting>(async () => {})
  const loadPipelineMetaRef = useRef<ReloadPipelineMeta>(async () => {})

  const pipeline = useRoutingPipelineTask({ loadRef, loadPipelineMetaRef })

  const routing = useRoutingData({
    nodeId: activeNode?.id ?? null,
    nodeLoading,
    syncActivePipelineTask: pipeline.syncActivePipelineTask,
    loadRef,
    loadPipelineMetaRef,
  })

  const selection = useProviderSelection(routing.data?.providers)

  const deploy = useDeployTargets({
    activeNodeId: activeNode?.id,
    selectedProviderFiles: selection.selectedProviderFiles,
    pendingRollbackStampRef: pipeline.pendingRollbackStampRef,
    recentRollbackStamp: pipeline.recentRollbackStamp,
  })

  const actions = useCidrPipelineActions({
    load: routing.load,
    providersCount: routing.data?.providers.length ?? 0,
    selectedProviderFiles: selection.selectedProviderFiles,
    setSelectedProviderFiles: selection.setSelectedProviderFiles,
    resolveSelectedProviderPayload: selection.resolveSelectedProviderPayload,
    deployAllOnline: deploy.deployAllOnline,
    deployTargetNodeIds: deploy.deployTargetNodeIds,
    setDeployPreview: deploy.setDeployPreview,
    setDeployPreviewLoading: deploy.setDeployPreviewLoading,
    attachPipelineTask: pipeline.attachPipelineTask,
    pipelineTask: pipeline.pipelineTask,
    pendingPipelineAction: pipeline.pendingPipelineAction,
    readonly,
  })

  const confirm = useConfirmAction({
    withPipelineAction: actions.withPipelineAction,
    withBackgroundTask: actions.withBackgroundTask,
    resolveSelectedProviderPayload: selection.resolveSelectedProviderPayload,
    selectedProviderFiles: selection.selectedProviderFiles,
    providersCount: routing.data?.providers.length ?? 0,
    filterAntifilter: actions.filterAntifilter,
    deployAllOnline: deploy.deployAllOnline,
    deployTargetNodeIds: deploy.deployTargetNodeIds,
    setDeployPreview: deploy.setDeployPreview,
    rollbackStamp: deploy.rollbackStamp,
    setRollbackStamp: deploy.setRollbackStamp,
    requestRollbackSelection: deploy.requestRollbackSelection,
  })

  return {
    data: routing.data,
    cidrDb: routing.cidrDb,
    antifilter: routing.antifilter,
    pipelineTask: pipeline.pipelineTask,
    pendingPipelineAction: pipeline.pendingPipelineAction,
    loading: routing.loading,
    refreshing: routing.refreshing,
    actionLoading: actions.actionLoading,
    pipelineBusy: actions.pipelineBusy,
    autoRefresh: routing.autoRefresh,
    setAutoRefresh: routing.setAutoRefresh,
    nextRefreshAt: routing.nextRefreshAt,
    /** Время последней завершённой задачи пайплайна — триггер перезапроса бюджета маршрутов. */
    lastTaskFinishedAt: pipeline.lastTaskFinishedAt,
    /** HA replica: routing is read-only on this node, mutating buttons must be disabled. */
    readonly,
    filterAntifilter: actions.filterAntifilter,
    setFilterAntifilter: actions.setFilterAntifilter,
    deployAllOnline: deploy.deployAllOnline,
    setDeployAllOnline: deploy.setDeployAllOnline,
    deployTargetNodeIds: deploy.deployTargetNodeIds,
    setDeployTargetNodeIds: deploy.setDeployTargetNodeIds,
    selectedProviderFiles: selection.selectedProviderFiles ?? [],
    setSelectedProviderFiles: selection.setSelectedProviderFiles,
    confirmAction: confirm.confirmAction,
    setConfirmAction: confirm.setConfirmAction,
    load: routing.load,
    withPipelineAction: actions.withPipelineAction,
    withAction: actions.withAction,
    executeConfirm: confirm.executeConfirm,
    toggleProvider: actions.toggleProvider,
    inline,
    refreshCidrDb: actions.refreshCidrDb,
    refreshOneProvider: actions.refreshOneProvider,
    retryFailedProviders: actions.retryFailedProviders,
    estimateCidr: actions.estimateCidr,
    refreshAntifilter: actions.refreshAntifilter,
    deployCidr: confirm.deployCidr,
    applyRouting: confirm.applyRouting,
    loadDeployPreview: actions.loadDeployPreview,
    deployPreview: deploy.deployPreview,
    deployPreviewLoading: deploy.deployPreviewLoading,
    requestRollback: confirm.requestRollback,
    rollbackStamp: deploy.rollbackStamp,
    recentRollbackStamp: deploy.recentRollbackStamp,
    customWizardOpen: actions.customWizardOpen,
    setCustomWizardOpen: actions.setCustomWizardOpen,
    customWizardLoading: actions.customWizardLoading,
    submitCustomProvider: actions.submitCustomProvider,
    clearCidrDbData: actions.clearCidrDbData,
  }
}
