import { ChevronRight } from 'lucide-react'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import {
  HealthScoreBadge,
  ResourceMetricInline,
} from '@/components/monitoring/nodeSummaryMetrics'
import { NodeStatusBadge } from '@/components/NodeSelector'
import { cn } from '@/lib/utils'
import type { MonitoringNodeSummary, NodeStatus } from '@/types'

type NodeSummaryCardProps = {
  node: MonitoringNodeSummary
  isActive: boolean
  onSelect: () => void
}

export default function NodeSummaryCard({ node, isActive, onSelect }: NodeSummaryCardProps) {
  const servicesIncomplete =
    node.total_services > 0 && node.active_services < node.total_services

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
          <div className="flex min-w-0 items-center gap-2">
            <ChevronRight
              size={14}
              className="shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
            />
            <span className="truncate font-medium">{node.node_name}</span>
            {isActive && (
              <span
                className="size-1.5 shrink-0 rounded-full bg-primary"
                title="Активный узел"
                aria-label="Активный узел"
              />
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <NodeStatusBadge status={node.status as NodeStatus} />
            <HealthScoreBadge score={node.health_score} level={node.health_level} />
            {node.error && <p className="mt-1 w-full text-[11px] text-destructive">{node.error}</p>}
          </div>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">OVPN</dt>
          <dd className="mt-0.5 font-mono text-sm font-medium tabular-nums">{node.connected_openvpn}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">WG</dt>
          <dd className="mt-0.5 font-mono text-sm font-medium tabular-nums">{node.connected_wireguard}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Службы</dt>
          <dd
            className={cn(
              'mt-0.5 font-mono text-sm font-medium tabular-nums',
              servicesIncomplete && 'text-amber-600 dark:text-amber-400',
            )}
          >
            {node.active_services}
            <span className="text-muted-foreground">/{node.total_services}</span>
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">CIDR</dt>
          <dd className="mt-0.5 font-mono text-sm font-medium tabular-nums">{node.cidr_routes_count ?? '—'}</dd>
        </div>
        <div className="col-span-2 sm:col-span-4">
          <dt className="text-muted-foreground">Трафик</dt>
          <dd className="mt-0.5 font-mono text-sm font-medium tabular-nums">
            {node.total_traffic_bytes != null ? formatBytes(node.total_traffic_bytes) : '—'}
          </dd>
        </div>
        <div className="col-span-1 sm:col-span-2">
          <dt className="mb-1.5 text-muted-foreground">CPU</dt>
          <dd>
            <ResourceMetricInline value={node.cpu_percent} label={`CPU ${node.node_name}`} />
          </dd>
        </div>
        <div className="col-span-1 sm:col-span-2">
          <dt className="mb-1.5 text-muted-foreground">RAM</dt>
          <dd>
            <ResourceMetricInline value={node.memory_percent} label={`RAM ${node.node_name}`} />
          </dd>
        </div>
      </dl>
    </button>
  )
}
