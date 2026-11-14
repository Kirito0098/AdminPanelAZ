import { GitBranch, Play, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
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
  autoRefresh: boolean
  /** When the next auto-refresh fires; the hook keeps the deadline, not the ticking counter. */
  nextRefreshAt: number | null
  refreshing: boolean
  pipelineBusy: boolean
  /** HA replica: routing data is shown read-only, mutations are refused by the hook. */
  readonly: boolean
  onToggleAutoRefresh: () => void
  onRefresh: () => void
  onSyncProviders: () => void
  onApplyDoall: () => void
}

function remainingSeconds(nextRefreshAt: number | null): number {
  if (nextRefreshAt === null) return REFRESH_INTERVAL
  const left = Math.ceil((nextRefreshAt - Date.now()) / 1000)
  return Math.min(REFRESH_INTERVAL, Math.max(0, left))
}

/** Second-by-second display only: re-renders the header alone, not the routing page tree. */
function useCountdown(nextRefreshAt: number | null, enabled: boolean): number {
  const [seconds, setSeconds] = useState(() => remainingSeconds(nextRefreshAt))

  useEffect(() => {
    setSeconds(remainingSeconds(nextRefreshAt))
    if (!enabled) return
    const id = window.setInterval(() => setSeconds(remainingSeconds(nextRefreshAt)), 1000)
    return () => window.clearInterval(id)
  }, [nextRefreshAt, enabled])

  return seconds
}

export default function RoutingPageHeader({
  nodeName,
  nodeStatus,
  autoRefresh,
  nextRefreshAt,
  refreshing,
  pipelineBusy,
  readonly,
  onToggleAutoRefresh,
  onRefresh,
  onSyncProviders,
  onApplyDoall,
}: RoutingPageHeaderProps) {
  const countdown = useCountdown(nextRefreshAt, autoRefresh)

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
          <Button
            variant="outline"
            size="sm"
            className="w-full sm:w-auto"
            disabled={pipelineBusy || readonly}
            onClick={onSyncProviders}
          >
            <RefreshCw size={14} className="mr-1.5" />
            Синхронизировать
          </Button>
          <Button
            size="sm"
            className="w-full sm:w-auto"
            disabled={pipelineBusy || readonly}
            onClick={onApplyDoall}
          >
            <Play size={14} className="mr-1.5" />
            Применить doall + client.sh 7
          </Button>
        </>
      }
    />
  )
}
