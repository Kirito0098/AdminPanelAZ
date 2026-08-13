import { Layers, Server } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { resolveProxyLinkTarget } from '@/lib/proxyLinkTarget'
import { cn } from '@/lib/utils'
import type { Node, NodeSyncGroup } from '@/types'

type ProxyLinkBadgeProps = {
  linkedVpnNodeId?: number | null
  nodes: Node[]
  syncGroups: NodeSyncGroup[]
  className?: string
  /** When true, show muted «не привязан» instead of hiding */
  showUnlinked?: boolean
}

export default function ProxyLinkBadge({
  linkedVpnNodeId,
  nodes,
  syncGroups,
  className,
  showUnlinked = false,
}: ProxyLinkBadgeProps) {
  const target = resolveProxyLinkTarget(linkedVpnNodeId, nodes, syncGroups)

  if (!target) {
    if (!showUnlinked) return null
    return (
      <Badge variant="outline" className={cn('text-[10px] font-normal text-muted-foreground', className)}>
        не привязан
      </Badge>
    )
  }

  const Icon = target.kind === 'ha' ? Layers : Server
  const variant = target.kind === 'missing' ? 'destructive' : 'secondary'

  return (
    <Badge
      variant={variant}
      className={cn('gap-1 text-[10px] font-normal', className)}
      title={
        target.kind === 'ha' && target.vpnNodeName
          ? `Прокси для HA-группы «${target.haGroupName}» (узел ${target.vpnNodeName})`
          : target.kind === 'vpn'
            ? `Прокси для сервера «${target.vpnNodeName}»`
            : `Привязка к отсутствующему узлу #${target.vpnNodeId}`
      }
    >
      <Icon size={10} className="shrink-0" />
      {target.kind === 'ha' ? `→ HA «${target.shortLabel}»` : `→ ${target.label}`}
    </Badge>
  )
}
