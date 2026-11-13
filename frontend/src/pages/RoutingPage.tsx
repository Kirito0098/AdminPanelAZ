import {
  CloudDownload,
  FlaskConical,
  LayoutDashboard,
  Route,
  Settings2,
} from 'lucide-react'
import { useCallback, useEffect, useMemo } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import HaReplicaBanner from '@/components/dashboard/HaReplicaBanner'
import AnalysisTab from '@/components/routing/AnalysisTab'
import ConfirmActionDialog from '@/components/routing/ConfirmActionDialog'
import CidrPipelineTab from '@/components/routing/CidrPipelineTab'
import CustomProviderWizardDialog from '@/components/routing/CustomProviderWizardDialog'
import PipelineStatusBar from '@/components/routing/PipelineStatusBar'
import PipelineTaskProgress from '@/components/routing/PipelineTaskProgress'
import ProvidersTab from '@/components/routing/ProvidersTab'
import RoutingOverviewTab from '@/components/routing/RoutingOverviewTab'
import RoutingPageHeader from '@/components/routing/RoutingPageHeader'
import RoutingPageSkeleton from '@/components/routing/RoutingPageSkeleton'
import RoutingSettingsTab from '@/components/routing/RoutingSettingsTab'
import RoutingWorkflowGuide from '@/components/routing/RoutingWorkflowGuide'
import { ROUTING_TAB_UPDATE, WORKFLOW_CHAIN } from '@/components/routing/routingLabels'
import { getRoutingWorkflowState, type RoutingTab } from '@/components/routing/routingWorkflow'
import { useRoutingPage } from '@/components/routing/useRoutingPage'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNode } from '@/context/NodeContext'
import { useAuth } from '@/context/AuthContext'

const ROUTING_TABS: Array<{ id: RoutingTab; label: string; shortLabel: string; icon: typeof Route; description: string }> = [
  {
    id: 'overview',
    label: 'Обзор',
    shortLabel: 'Обзор',
    icon: LayoutDashboard,
    description: 'Сводка маршрутов, статус обновления списков и быстрые переходы',
  },
  {
    id: 'analysis',
    label: 'Анализ',
    shortLabel: 'Анализ',
    icon: FlaskConical,
    description: 'Разбор лога DPI checker и рекомендации по включению CIDR-списков',
  },
  {
    id: 'pipeline',
    label: ROUTING_TAB_UPDATE,
    shortLabel: ROUTING_TAB_UPDATE,
    icon: CloudDownload,
    description: `${WORKFLOW_CHAIN}: подготовка списков CIDR (администратор)`,
  },
  {
    id: 'providers',
    label: 'Провайдеры',
    shortLabel: 'Списки',
    icon: Route,
    description: 'Включение CIDR-списков для маршрутизации на активном узле',
  },
  {
    id: 'settings',
    label: 'Настройки',
    shortLabel: 'Настр.',
    icon: Settings2,
    description: 'Автообновление базы CIDR и параметры расписания',
  },
]

const TAB_IDS = new Set<RoutingTab>(ROUTING_TABS.map((item) => item.id))

/**
 * Admin-only page: the role is checked before the content mounts, because its hook
 * starts loading routing data right away (a non-admin would only collect 403 toasts).
 */
export default function RoutingPage() {
  const { user } = useAuth()
  const [searchParams] = useSearchParams()
  const isAdmin = user?.role === 'admin'

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  if (searchParams.get('tab') === 'antizapret-config') {
    return <Navigate to="/protocols/antizapret" replace />
  }

  if (searchParams.get('tab') === 'files') {
    return <Navigate to="/routing?tab=overview" replace />
  }

  return <RoutingPageContent />
}

function RoutingPageContent() {
  const { activeNode, nodes, syncGroups } = useNode()
  const [searchParams, setSearchParams] = useSearchParams()
  // Развёртывать можно и на реплику (ремонт), но в списке видно, что она реплика:
  // файлы туда обычно приезжают сами с primary.
  const replicaNodeIds = useMemo(
    () => new Set(syncGroups.flatMap((group) => group.replica_node_ids ?? [])),
    [syncGroups],
  )

  const tab = useMemo(() => {
    const value = searchParams.get('tab') as RoutingTab | null
    return value && TAB_IDS.has(value) ? value : 'overview'
  }, [searchParams])

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
    nextRefreshAt,
    lastTaskFinishedAt,
    readonly,
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
    estimateCidr,
    refreshAntifilter,
    deployCidr,
    applyRouting,
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
    () => (data ? getRoutingWorkflowState(data.providers, cidrDb) : null),
    [data, cidrDb],
  )

  // Budget endpoint reads the last estimate/artifacts: refetch it when a build, deploy or estimate finished.
  const budgetVersion = useMemo(
    () =>
      [
        lastTaskFinishedAt,
        cidrDb?.last_compile_at?.finished_at,
        cidrDb?.last_deploy?.finished_at,
        cidrDb?.last_refresh_finished,
      ]
        .filter(Boolean)
        .join('|'),
    [lastTaskFinishedAt, cidrDb],
  )

  const activeTabMeta = ROUTING_TABS.find((item) => item.id === tab)

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
      <HaReplicaBanner />
      <RoutingPageHeader
        nodeName={activeNode?.name ?? data.node_name}
        nodeStatus={activeNode?.status}
        autoRefresh={autoRefresh}
        nextRefreshAt={nextRefreshAt}
        refreshing={refreshing}
        pipelineBusy={pipelineBusy}
        readonly={readonly}
        onToggleAutoRefresh={() => setAutoRefresh((v) => !v)}
        onRefresh={() => load({ manual: true })}
        onSyncProviders={() => setConfirmAction('sync-providers')}
        onApplyDoall={applyRouting}
      />

      <RoutingWorkflowGuide workflow={workflow} pipelineBusy={pipelineBusy} onNavigate={navigateTab} />

      <PipelineTaskProgress task={pipelineTask} />

      <Tabs value={tab} onValueChange={(value) => navigateTab(value as RoutingTab)} className="space-y-4">
        <div className="space-y-2">
          <TabsList className="flex h-auto w-full flex-wrap gap-1 bg-muted/50 p-1">
            {ROUTING_TABS.map((item) => (
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
          <RoutingOverviewTab
            data={data}
            antifilter={antifilter}
            workflow={workflow}
            budgetVersion={budgetVersion}
          />
        </TabsContent>

        <TabsContent value="analysis" className="mt-0">
          <AnalysisTab providers={data.providers} onNavigateTab={navigateTab} />
        </TabsContent>

        <TabsContent value="pipeline" className="mt-0">
          <CidrPipelineTab
            providers={data.providers}
            cidrDb={cidrDb}
            antifilter={antifilter}
            pipelineTask={pipelineTask}
            pendingPipelineAction={pendingPipelineAction}
            nodes={nodes}
            replicaNodeIds={replicaNodeIds}
            deployAllOnline={deployAllOnline}
            deployTargetNodeIds={deployTargetNodeIds}
            selectedProviderFiles={selectedProviderFiles}
            filterAntifilter={filterAntifilter}
            pipelineBusy={pipelineBusy}
            readonly={readonly}
            onEstimate={estimateCidr}
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

        <TabsContent value="settings" className="mt-0">
          <RoutingSettingsTab />
        </TabsContent>

        <TabsContent value="providers" className="mt-0">
          <ProvidersTab
            providers={data.providers}
            cidrDb={cidrDb}
            activeNode={activeNode}
            readonly={readonly}
            actionLoading={actionLoading}
            pipelineBusy={pipelineBusy}
            onToggle={toggleProvider}
            onApplyRouting={applyRouting}
            onNavigateTab={navigateTab}
            workflow={workflow}
          />
        </TabsContent>
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
