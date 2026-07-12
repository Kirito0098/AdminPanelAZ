import { ChevronRight } from 'lucide-react'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import { NodeStatusBadge } from '@/components/NodeSelector'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { metricBarClass } from '@/lib/metricColors'
import { cn } from '@/lib/utils'
import type { MonitoringNodeSummary, NodeStatus } from '@/types'

function formatMetricPercent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

type NodeSummaryCardProps = {
  node: MonitoringNodeSummary
  isActive: boolean
  onSelect: () => void
}

export default function NodeSummaryCard({ node, isActive, onSelect }: NodeSummaryCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'group w-full rounded-xl border p-4 text-left transition-colors',
        node.status === 'offline' && 'border-destructive/30 bg-destructive/5 hover:bg-destructive/10',
        node.status !== 'offline' && 'border-border/80 bg-card hover:border-primary/30 hover:bg-muted/30',
        isActive && 'ring-1 ring-primary/25',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <ChevronRight
              size={14}
              className="shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
            />
            <span className="truncate font-medium">{node.node_name}</span>
            {isActive && (
              <Badge variant="outline" className="h-4 px-1 text-[10px]">
                активный
              </Badge>
            )}
          </div>
          <div className="mt-2">
            <NodeStatusBadge status={node.status as NodeStatus} />
            {node.error && <p className="mt-1 text-[11px] text-destructive">{node.error}</p>}
          </div>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
        <div>
          <dt className="text-muted-foreground">OpenVPN</dt>
          <dd className="mono mt-0.5 font-medium tabular-nums">{node.connected_openvpn}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">WireGuard</dt>
          <dd className="mono mt-0.5 font-medium tabular-nums">{node.connected_wireguard}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Службы</dt>
          <dd className="mono mt-0.5 font-medium tabular-nums">
            {node.active_services}/{node.total_services}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">CIDR</dt>
          <dd className="mono mt-0.5 font-medium tabular-nums">{node.cidr_routes_count ?? '—'}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-muted-foreground">Трафик</dt>
          <dd className="mono mt-0.5 font-medium tabular-nums">
            {node.total_traffic_bytes != null ? formatBytes(node.total_traffic_bytes) : '—'}
          </dd>
        </div>
        <div>
          <dt className="mb-1 text-muted-foreground">CPU</dt>
          <dd>
            {node.cpu_percent != null ? (
              <div className="space-y-1">
                <Progress
                  value={Math.min(100, node.cpu_percent)}
                  barClassName={metricBarClass(node.cpu_percent)}
                  className="h-2"
                />
                <span className="text-[10px] text-muted-foreground">{formatMetricPercent(node.cpu_percent)}</span>
              </div>
            ) : (
              <span className="text-muted-foreground">н/д</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="mb-1 text-muted-foreground">RAM</dt>
          <dd>
            {node.memory_percent != null ? (
              <div className="space-y-1">
                <Progress
                  value={Math.min(100, node.memory_percent)}
                  barClassName={metricBarClass(node.memory_percent)}
                  className="h-2"
                />
                <span className="text-[10px] text-muted-foreground">{formatMetricPercent(node.memory_percent)}</span>
              </div>
            ) : (
              <span className="text-muted-foreground">н/д</span>
            )}
          </dd>
        </div>
      </dl>
    </button>
  )
}
