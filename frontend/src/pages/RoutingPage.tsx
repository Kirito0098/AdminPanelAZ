import {
  CloudDownload,
  LayoutDashboard,
  Route,
} from 'lucide-react'
import { useCallback, useEffect, useMemo } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import ConfirmActionDialog from '@/components/routing/ConfirmActionDialog'
import CidrPipelineTab from '@/components/routing/CidrPipelineTab'
import CustomProviderWizardDialog from '@/components/routing/CustomProviderWizardDialog'
import PipelineStatusBar from '@/components/routing/PipelineStatusBar'
import PipelineTaskProgress from '@/components/routing/PipelineTaskProgress'
import ProvidersTab from '@/components/routing/ProvidersTab'
import RoutingOverviewTab from '@/components/routing/RoutingOverviewTab'
import RoutingPageHeader from '@/components/routing/RoutingPageHeader'
import RoutingPageSkeleton from '@/components/routing/RoutingPageSkeleton'
import RoutingSectionCards from '@/components/routing/RoutingSectionCards'
import RoutingWorkflowGuide from '@/components/routing/RoutingWorkflowGuide'
import { getRoutingWorkflowState, type RoutingTab } from '@/components/routing/routingWorkflow'
import { useRoutingPage } from '@/components/routing/useRoutingPage'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNode } from '@/context/NodeContext'
import { useAuth } from '@/context/AuthContext'

const ROUTING_TABS: Array<{ id: RoutingTab; label: string; shortLabel: string; icon: typeof Route; description: string; adminOnly?: boolean }> = [
  {
    id: 'overview',
    label: 'Обзор',
    shortLabel: 'Обзор',
    icon: LayoutDashboard,
    description: 'Сводка маршрутов, статус pipeline и быстрые переходы',
  },
  {
    id: 'providers',
    label: 'Провайдеры',
    shortLabel: 'Списки',
    icon: Route,
    description: 'Включение CIDR-списков для маршрутизации на активном узле',
  },
  {
    id: 'pipeline',
    label: 'Pipeline',
    shortLabel: 'Pipeline',
    icon: CloudDownload,
    description: 'Ingest → compile → deploy: обновление списков (администратор)',
    adminOnly: true,
  },
]

const PUBLIC_TABS = new Set<RoutingTab>(['overview', 'providers'])

export default function RoutingPage() {
  const { user } = useAuth()
  const { activeNode, nodes } = useNode()
  const isAdmin = user?.role === 'admin'
  const [searchParams, setSearchParams] = useSearchParams()

  const tab = useMemo(() => {
    const value = searchParams.get('tab') as RoutingTab | null
    if (value && PUBLIC_TABS.has(value)) return value
    if (value === 'pipeline' && isAdmin) return value
    return 'overview'
  }, [searchParams, isAdmin])

  const navigateTab = useCallback(
    (next: RoutingTab, anchor?: string) => {
      setSearchParams({ tab: next }, { replace: true })
      if (anchor) {
        requestAnimationFrame(() => {
          document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        })
      }
    },
    [setSearchParams],
  )

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, '')
    if (!hash) return
    const timer = window.setTimeout(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 150)
    return () => window.clearTimeout(timer)
  }, [tab])

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
    deployCidrAndApply,
    clearCidrDbData,
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
  } = useRoutingPage()

  const workflow = useMemo(
    () => (data ? getRoutingWorkflowState(data.providers, cidrDb, isAdmin) : null),
    [data, cidrDb, isAdmin],
  )

  const visibleTabs = ROUTING_TABS.filter((item) => !item.adminOnly || isAdmin)
  const activeTabMeta = visibleTabs.find((item) => item.id === tab)

  if (loading && !data) {
    return <RoutingPageSkeleton />
  }

  if (!data || !workflow) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        Не удалось загрузить данные маршрутизации
      </div>
    )
  }

  return (
    <div className="space-y-5">
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

      <RoutingWorkflowGuide
        workflow={workflow}
        isAdmin={isAdmin}
        pipelineBusy={pipelineBusy}
        onNavigate={navigateTab}
      />

      <RoutingSectionCards
        workflow={workflow}
        isAdmin={isAdmin}
        activeTab={tab}
        onNavigate={navigateTab}
      />

      <PipelineTaskProgress task={pipelineTask} />

      <Tabs value={tab} onValueChange={(value) => navigateTab(value as RoutingTab)} className="space-y-4">
        <div className="space-y-2">
          <TabsList className="flex h-auto w-full flex-wrap gap-1 bg-muted/50 p-1">
            {visibleTabs.map((item) => (
              <TabsTrigger key={item.id} value={item.id} className="gap-1.5 flex-1 sm:flex-none">
                <item.icon size={14} />
                <span className="hidden sm:inline">{item.label}</span>
                <span className="sm:hidden">{item.shortLabel}</span>
              </TabsTrigger>
            ))}
          </TabsList>
          {activeTabMeta && (
            <p className="text-xs text-muted-foreground px-1">{activeTabMeta.description}</p>
          )}
        </div>

        <TabsContent value="overview" className="space-y-5 mt-0">
          <PipelineStatusBar cidrDb={cidrDb} antifilter={antifilter} />
          <RoutingOverviewTab data={data} cidrDb={cidrDb} antifilter={antifilter} workflow={workflow} />
        </TabsContent>

        <TabsContent value="providers" className="mt-0">
          <ProvidersTab
            providers={data.providers}
            cidrDb={cidrDb}
            activeNode={activeNode}
            isAdmin={isAdmin}
            actionLoading={actionLoading}
            pipelineBusy={pipelineBusy}
            onToggle={toggleProvider}
            onNavigateTab={navigateTab}
            workflow={workflow}
          />
        </TabsContent>

        {isAdmin && (
          <TabsContent value="pipeline" className="mt-0">
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
              onDeployAndApply={deployCidrAndApply}
              onClearDb={clearCidrDbData}
              onOpenCustomWizard={() => setCustomWizardOpen(true)}
              onLoadDeployPreview={loadDeployPreview}
              deployPreview={deployPreview}
              deployPreviewLoading={deployPreviewLoading}
              onRollback={requestRollback}
              recentRollbackStamp={recentRollbackStamp}
              workflow={workflow}
            />
          </TabsContent>
        )}
      </Tabs>

      <ConfirmActionDialog
        action={confirmAction}
        onClose={() => setConfirmAction(null)}
        onConfirm={executeConfirm}
        loading={actionLoading}
        deployPreview={deployPreview}
        rollbackStamp={rollbackStamp}
        rollbackMtime={
          rollbackStamp
            ? cidrDb?.runtime_backups?.find((b) => b.stamp === rollbackStamp)?.mtime
            : undefined
        }
      />

      <CustomProviderWizardDialog
        open={customWizardOpen}
        onOpenChange={setCustomWizardOpen}
        providers={data.providers}
        loading={customWizardLoading}
        onSubmit={submitCustomProvider}
      />
    </div>
  )
}
