import { Check, Globe, Server } from 'lucide-react'
import ProxyNodePanel from '@/components/nodes/ProxyNodePanel'
import ProxyLinkBadge from '@/components/proxy/ProxyLinkBadge'
import { NodeStatusBadge } from '@/components/NodeSelector'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { Node, NodeSyncGroup } from '@/types'
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
  onEnableMtls: () => void
  onDisableMtls: () => void
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
  onEnableMtls,
  onDisableMtls,
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
    <Card className={cn(isActive && 'border-primary/40 bg-primary/5')}>
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
              <span className="truncate">{node.name}</span>
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
            <CardDescription className="font-mono text-xs">{address}</CardDescription>
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
          onEnableMtls={onEnableMtls}
          onDisableMtls={onDisableMtls}
          onEdit={onEdit}
          onDelete={onDelete}
        />
      </CardContent>
    </Card>
  )
}
