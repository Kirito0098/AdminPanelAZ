import { GitBranch, Play, RefreshCw } from 'lucide-react'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import { NodeBadge } from '@/components/NodeSelector'
import { Button } from '@/components/ui/button'
import { REFRESH_INTERVAL } from './useRoutingPage'

interface RoutingPageHeaderProps {
  nodeName?: string | null
  nodeStatus?: import('@/types').NodeStatus
  isAdmin: boolean
  autoRefresh: boolean
  countdown: number
  refreshing: boolean
  pipelineBusy: boolean
  onToggleAutoRefresh: () => void
  onRefresh: () => void
  onSyncProviders: () => void
  onApplyDoall: () => void
}

export default function RoutingPageHeader({
  nodeName,
  nodeStatus,
  isAdmin,
  autoRefresh,
  countdown,
  refreshing,
  pipelineBusy,
  onToggleAutoRefresh,
  onRefresh,
  onSyncProviders,
  onApplyDoall,
}: RoutingPageHeaderProps) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between lg:gap-4">
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <GitBranch size={22} />
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-bold tracking-tight">Маршрутизация / CIDR</h2>
            <NodeBadge name={nodeName} status={nodeStatus} />
          </div>
          <p className="text-sm text-muted-foreground">
            CIDR-списки провайдеров, обновление списков и маршруты AntiZapret
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <AutoRefreshControl
          enabled={autoRefresh}
          countdown={countdown}
          intervalSec={REFRESH_INTERVAL}
          refreshing={refreshing}
          onToggle={onToggleAutoRefresh}
          onManualRefresh={onRefresh}
        />
        {isAdmin && (
          <>
            <Button
              variant="outline"
              size="sm"
              className="w-full sm:w-auto"
              disabled={pipelineBusy}
              onClick={onSyncProviders}
            >
              <RefreshCw size={14} className="mr-1.5" />
              Синхронизировать
            </Button>
            <Button size="sm" className="w-full sm:w-auto" disabled={pipelineBusy} onClick={onApplyDoall}>
              <Play size={14} className="mr-1.5" />
              Применить doall + client.sh 7
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
