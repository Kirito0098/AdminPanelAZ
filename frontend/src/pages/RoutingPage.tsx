import {
  CloudDownload,
  LayoutDashboard,
  Route,
} from 'lucide-react'
import { useMemo } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import ConfirmActionDialog from '@/components/routing/ConfirmActionDialog'
import CidrPipelineTab from '@/components/routing/CidrPipelineTab'
import PipelineStatusBar from '@/components/routing/PipelineStatusBar'
import PipelineTaskProgress from '@/components/routing/PipelineTaskProgress'
import ProvidersTab from '@/components/routing/ProvidersTab'
import RoutingOverviewTab from '@/components/routing/RoutingOverviewTab'
import RoutingPageHeader from '@/components/routing/RoutingPageHeader'
import RoutingPageSkeleton from '@/components/routing/RoutingPageSkeleton'
import { useRoutingPage } from '@/components/routing/useRoutingPage'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNode } from '@/context/NodeContext'
import { useAuth } from '@/context/AuthContext'

export default function RoutingPage() {
  const { user } = useAuth()
  const { activeNode, nodes } = useNode()
  const isAdmin = user?.role === 'admin'
  const [searchParams] = useSearchParams()

  const initialRoutingTab = useMemo(() => {
    const tab = searchParams.get('tab')
    const publicTabs = new Set(['overview', 'providers'])
    const adminTabs = new Set(['pipeline'])
    if (tab && publicTabs.has(tab)) return tab
    if (tab && adminTabs.has(tab) && isAdmin) return tab
    return 'overview'
  }, [searchParams, isAdmin])

  if (searchParams.get('tab') === 'antizapret-config') {
    return <Navigate to="/antizapret" replace />
  }

  if (searchParams.get('tab') === 'files') {
    return <Navigate to="/routing?tab=overview" replace />
  }

  const {
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
    selectedProviderFiles,
    setSelectedProviderFiles,
    confirmAction,
    setConfirmAction,
    load,
    executeConfirm,
    toggleProvider,
    refreshCidrDb,
    refreshOneProvider,
    retryFailedProviders,
    refreshAntifilter,
    deployCidr,
    clearCidrDbData,
  } = useRoutingPage()

  if (loading && !data) {
    return <RoutingPageSkeleton />
  }

  if (!data) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        Не удалось загрузить данные маршрутизации
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <RoutingPageHeader
        nodeName={activeNode?.name ?? data.node_name}
        nodeStatus={activeNode?.status}
        isAdmin={isAdmin}
        autoRefresh={autoRefresh}
        countdown={countdown}
        refreshing={refreshing}
        pipelineBusy={pipelineBusy}
        onToggleAutoRefresh={() => setAutoRefresh((v) => !v)}
        onRefresh={() => load({ manual: true })}
        onSyncProviders={() => setConfirmAction('sync-providers')}
        onApplyDoall={() => setConfirmAction('apply-doall')}
      />

      <PipelineTaskProgress task={pipelineTask} />

      <PipelineStatusBar cidrDb={cidrDb} antifilter={antifilter} />

      <Tabs defaultValue={initialRoutingTab} key={initialRoutingTab} className="space-y-4">
        <TabsList className="flex h-auto flex-wrap gap-1 bg-muted/50 p-1">
          <TabsTrigger value="overview" className="gap-1.5">
            <LayoutDashboard size={14} />
            <span className="hidden sm:inline">Обзор</span>
          </TabsTrigger>
          <TabsTrigger value="providers" className="gap-1.5">
            <Route size={14} />
            <span className="hidden sm:inline">Провайдеры</span>
          </TabsTrigger>
          {isAdmin && (
            <TabsTrigger value="pipeline" className="gap-1.5">
              <CloudDownload size={14} />
              <span className="hidden sm:inline">CIDR Pipeline</span>
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="overview">
          <RoutingOverviewTab data={data} cidrDb={cidrDb} antifilter={antifilter} />
        </TabsContent>

        <TabsContent value="providers">
          <ProvidersTab
            providers={data.providers}
            cidrDb={cidrDb}
            activeNode={activeNode}
            isAdmin={isAdmin}
            actionLoading={actionLoading}
            pipelineBusy={pipelineBusy}
            onToggle={toggleProvider}
            onRefreshOne={refreshOneProvider}
          />
        </TabsContent>

        {isAdmin && (
          <TabsContent value="pipeline">
            <CidrPipelineTab
              providers={data.providers}
              cidrDb={cidrDb}
              antifilter={antifilter}
              pipelineTask={pipelineTask}
              pendingPipelineAction={pendingPipelineAction}
              nodes={nodes}
              deployAllOnline={deployAllOnline}
              deployTargetNodeIds={deployTargetNodeIds}
              selectedProviderFiles={selectedProviderFiles}
              filterAntifilter={filterAntifilter}
              pipelineBusy={pipelineBusy}
              onFilterAntifilterChange={setFilterAntifilter}
              onDeployAllOnlineChange={setDeployAllOnline}
              onDeployTargetNodeIdsChange={setDeployTargetNodeIds}
              onSelectedProviderFilesChange={setSelectedProviderFiles}
              onRefreshDb={refreshCidrDb}
              onRetryFailedProviders={retryFailedProviders}
              onRefreshOne={refreshOneProvider}
              onRefreshAntifilter={refreshAntifilter}
              onGenerate={() => setConfirmAction('generate-only')}
              onDeploy={deployCidr}
              onGenerateDoall={() => setConfirmAction('generate-doall')}
              onClearDb={clearCidrDbData}
            />
          </TabsContent>
        )}

      </Tabs>

      <ConfirmActionDialog
        action={confirmAction}
        onClose={() => setConfirmAction(null)}
        onConfirm={executeConfirm}
        loading={actionLoading}
      />
    </div>
  )
}
