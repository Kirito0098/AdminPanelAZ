import {
  CloudDownload,
  FileText,
  Gamepad2,
  LayoutDashboard,
  Layers,
  Route,
  Settings2,
} from 'lucide-react'
import AntizapretConfigTab from '@/components/routing/AntizapretConfigTab'
import ConfirmActionDialog from '@/components/routing/ConfirmActionDialog'
import CidrPipelineTab from '@/components/routing/CidrPipelineTab'
import FilesTab from '@/components/routing/FilesTab'
import GameFiltersTab from '@/components/routing/GameFiltersTab'
import PipelineStatusBar from '@/components/routing/PipelineStatusBar'
import PipelineTaskProgress from '@/components/routing/PipelineTaskProgress'
import PresetsTab from '@/components/routing/PresetsTab'
import ProvidersTab from '@/components/routing/ProvidersTab'
import RoutingOverviewTab from '@/components/routing/RoutingOverviewTab'
import RoutingPageHeader from '@/components/routing/RoutingPageHeader'
import RoutingPageSkeleton from '@/components/routing/RoutingPageSkeleton'
import { useRoutingPage } from '@/components/routing/useRoutingPage'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNode } from '@/context/NodeContext'
import { useAuth } from '@/context/AuthContext'

export default function RoutingPage() {
  const { user } = useAuth()
  const { activeNode, nodes } = useNode()
  const isAdmin = user?.role === 'admin'

  const {
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
    executeConfirm,
    toggleProvider,
    applyPreset,
    syncGames,
    refreshCidrDb,
    refreshAntifilter,
    deployCidr,
    inline,
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

      <InlineProgressBar active={inline.active} label={inline.label} />
      <PipelineTaskProgress task={pipelineTask} />

      <PipelineStatusBar cidrDb={cidrDb} antifilter={antifilter} />

      <Tabs defaultValue="overview" className="space-y-4">
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
          <TabsTrigger value="presets" className="gap-1.5">
            <Layers size={14} />
            <span className="hidden sm:inline">Пресеты</span>
          </TabsTrigger>
          <TabsTrigger value="files" className="gap-1.5">
            <FileText size={14} />
            <span className="hidden sm:inline">Файлы</span>
          </TabsTrigger>
          <TabsTrigger value="games" className="gap-1.5">
            <Gamepad2 size={14} />
            <span className="hidden sm:inline">Игровые фильтры</span>
          </TabsTrigger>
          {isAdmin && (
            <TabsTrigger value="antizapret-config" className="gap-1.5">
              <Settings2 size={14} />
              <span className="hidden sm:inline">Конфиг AntiZapret</span>
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
            isAdmin={isAdmin}
            actionLoading={actionLoading}
            onToggle={toggleProvider}
          />
        </TabsContent>

        {isAdmin && (
          <TabsContent value="pipeline">
            <CidrPipelineTab
              cidrDb={cidrDb}
              antifilter={antifilter}
              pipelineTask={pipelineTask}
              nodes={nodes}
              deployAllOnline={deployAllOnline}
              deployTargetNodeIds={deployTargetNodeIds}
              filterAntifilter={filterAntifilter}
              pipelineBusy={pipelineBusy}
              onFilterAntifilterChange={setFilterAntifilter}
              onDeployAllOnlineChange={setDeployAllOnline}
              onDeployTargetNodeIdsChange={setDeployTargetNodeIds}
              onRefreshDb={refreshCidrDb}
              onRefreshAntifilter={refreshAntifilter}
              onGenerate={() => setConfirmAction('generate-only')}
              onDeploy={deployCidr}
              onGenerateDoall={() => setConfirmAction('generate-doall')}
            />
          </TabsContent>
        )}

        <TabsContent value="presets">
          <PresetsTab
            providers={data.providers}
            isAdmin={isAdmin}
            actionLoading={actionLoading}
            onApply={applyPreset}
          />
        </TabsContent>

        <TabsContent value="files">
          <FilesTab isAdmin={isAdmin} />
        </TabsContent>

        <TabsContent value="games">
          <GameFiltersTab
            games={games}
            gameModes={gameModes}
            isAdmin={isAdmin}
            actionLoading={actionLoading}
            onModeChange={(key, mode) => setGameModes((prev) => ({ ...prev, [key]: mode }))}
            onSync={syncGames}
          />
        </TabsContent>

        {isAdmin && (
          <TabsContent value="antizapret-config">
            <AntizapretConfigTab />
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
