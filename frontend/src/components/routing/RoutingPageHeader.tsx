import { GitBranch, Play, RefreshCw } from 'lucide-react'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import { NodeBadge } from '@/components/NodeSelector'
import { Button } from '@/components/ui/button'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import { DOCS } from '@/lib/docsUrls'
import { REFRESH_INTERVAL } from './useRoutingPage'
import type { NodeStatus } from '@/types'

interface RoutingPageHeaderProps {
  nodeName?: string | null
  nodeStatus?: NodeStatus
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
    <PageSectionHeader
      card
      icon={GitBranch}
      title="Маршрутизация / CIDR"
      titleAddon={<NodeBadge name={nodeName} status={nodeStatus} />}
      description="CIDR-списки провайдеров, обновление списков и маршруты AntiZapret"
      docsHref={DOCS.routing}
      actions={
        <>
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
        </>
      }
    />
  )
}
