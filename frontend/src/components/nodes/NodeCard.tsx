import { Check, Globe, Server } from 'lucide-react'
import ProxyNodePanel from '@/components/nodes/ProxyNodePanel'
import ProxyLinkBadge from '@/components/proxy/ProxyLinkBadge'
import { NodeStatusBadge } from '@/components/NodeSelector'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { Node, NodeSyncGroup, NodeTransportId } from '@/types'
import NodeActions from './NodeActions'
import NodeConnectionErrorAlert from './NodeConnectionErrorAlert'
import NodeTransportBadge from './NodeTransportBadge'
import { formatLastSeen, getNodeMeta } from './nodeHelpers'
import { isProxyNode } from './nodeKind'

export type NodeCardProps = {
  node: Node
  isActive: boolean
  showProxyUi: boolean
  nodes: Node[]
  syncGroups: NodeSyncGroup[]
  healthLoading: boolean
  activateLoading: boolean
  selected?: boolean
  onToggleSelect?: () => void
  onActivate: () => void
  onHealth: () => void
  onUpdate: () => void
  onRestart: () => void
  onRotateKey: () => void
  onTransportChange: (transport: NodeTransportId) => void
  onEdit: () => void
  onDelete: () => void
  onProxyUpdated?: () => void | Promise<void>
}

export default function NodeCard({
  node,
  isActive,
  showProxyUi,
  nodes,
  syncGroups,
  healthLoading,
  activateLoading,
  selected = false,
  onToggleSelect,
  onActivate,
  onHealth,
  onUpdate,
  onRestart,
  onRotateKey,
  onTransportChange,
  onEdit,
  onDelete,
  onProxyUpdated,
}: NodeCardProps) {
  const meta = getNodeMeta(node)
  const lastSeen = formatLastSeen(node.last_seen_at)
  const address = node.is_local ? 'local' : `${node.host}:${node.port}`
  const isProxy = isProxyNode(node)
  const showProxyAffordance = showProxyUi && isProxy

  return (
    <Card
      className={cn(
        'overflow-hidden border-border/70 transition-colors',
        isActive && 'border-primary/40 bg-primary/[0.04]',
        node.status === 'offline' && !isActive && 'border-destructive/20',
      )}
    >
      <div
        className={cn(
          'h-1 w-full',
          isActive
            ? 'bg-primary'
            : node.status === 'online'
              ? 'bg-emerald-500/70'
              : node.status === 'offline'
                ? 'bg-destructive/70'
                : 'bg-muted-foreground/30',
        )}
        aria-hidden
      />
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 space-y-1">
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              {onToggleSelect && (
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={onToggleSelect}
                  aria-label={`Выбрать ${node.name}`}
                  className="h-4 w-4 rounded border"
                />
              )}
              <Server size={16} className="shrink-0 text-muted-foreground" />
              <span className="truncate font-semibold tracking-tight">{node.name}</span>
              {isProxy && (
                <Badge variant="outline" className="border-amber-500/40 text-[10px] text-amber-800 dark:text-amber-100">
                  Прокси
                </Badge>
              )}
              {isProxy && !showProxyUi && (
                <Badge variant="secondary" className="text-[10px]">
                  модуль выкл
                </Badge>
              )}
              {showProxyAffordance && (
                <ProxyLinkBadge
                  linkedVpnNodeId={node.linked_vpn_node_id}
                  nodes={nodes}
                  syncGroups={syncGroups}
                  showUnlinked
                />
              )}
              {isActive && (
                <Badge variant="default" className="text-[10px]">
                  <Check size={10} />
                  активный
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="font-mono text-xs tabular-nums text-muted-foreground">
              {address}
            </CardDescription>
          </div>
          <NodeStatusBadge status={node.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <div>
            <p className="text-xs text-muted-foreground">IP сервера</p>
            <p className="font-mono text-xs">{meta.serverIp ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Службы</p>
            <p>{meta.servicesLabel ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Agent</p>
            <p className="font-mono text-xs">{meta.agentVersion ?? '—'}</p>
          </div>
        </div>
        <div className="rounded-md border border-border/60 bg-muted/20 p-3 space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Связь</p>
          <div className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
            <div>
              <span className="text-muted-foreground">TLS </span>
              {meta.listenTls === null && meta.expectedTls === null ? (
                <span>— (обновите агент ≥1.8)</span>
              ) : (
                <span>
                  факт {meta.listenTls == null ? '—' : meta.listenTls ? 'HTTPS' : 'HTTP'}
                  {' / '}
                  ожид. {meta.expectedTls == null ? '—' : meta.expectedTls ? 'HTTPS' : 'HTTP'}
                  {meta.tlsMismatch ? ' · mismatch' : ''}
                </span>
              )}
            </div>
            <div>
              <span className="text-muted-foreground">Uptime </span>
              <span>
                {meta.uptimeSec == null
                  ? '—'
                  : meta.uptimeSec < 120
                    ? `${meta.uptimeSec} с`
                    : `${Math.floor(meta.uptimeSec / 60)} мин`}
              </span>
            </div>
            <div className="sm:col-span-2">
              <span className="text-muted-foreground">Последний ok </span>
              <span>{meta.lastHealthOkAt ? formatLastSeen(meta.lastHealthOkAt) : '—'}</span>
            </div>
            {meta.lastLinkError?.message && (
              <div className="sm:col-span-2 text-amber-800 dark:text-amber-100">
                <span className="font-mono">{meta.lastLinkError.code ?? 'error'}</span>
                {': '}
                {meta.lastLinkError.message}
                {meta.lastLinkError.hint ? ` — ${meta.lastLinkError.hint}` : ''}
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {node.is_local ? (
            <Badge variant="secondary">Локальный</Badge>
          ) : (
            <Badge variant="outline">
              <Globe size={10} />
              Удалённый
            </Badge>
          )}
          <NodeTransportBadge node={node} />
          {lastSeen && <span>Последняя проверка: {lastSeen}</span>}
        </div>
        {node.status === 'offline' && meta.lastError && (
          <NodeConnectionErrorAlert node={node} lastError={meta.lastError} />
        )}
        {showProxyAffordance && (
          <ProxyNodePanel
            node={node}
            nodes={nodes}
            syncGroups={syncGroups}
            onUpdated={onProxyUpdated}
          />
        )}
        <NodeActions
          node={node}
          isActive={isActive}
          isProxy={isProxy}
          healthLoading={healthLoading}
          activateLoading={activateLoading}
          onActivate={onActivate}
          onHealth={onHealth}
          onUpdate={onUpdate}
          onRestart={onRestart}
          onRotateKey={onRotateKey}
          onTransportChange={onTransportChange}
          onEdit={onEdit}
          onDelete={onDelete}
        />
      </CardContent>
    </Card>
  )
}
