import type { LucideIcon } from 'lucide-react'
import { Activity, CircleCheck, CircleX, HelpCircle, Server } from 'lucide-react'
import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import { NODE_STATUS_LABELS } from '@/lib/uiLabels'
import type { NodeStatus } from '@/types'

export const statusLabels = NODE_STATUS_LABELS

const statusColors: Record<NodeStatus, string> = {
  online: 'bg-emerald-500',
  offline: 'bg-red-500',
  unknown: 'bg-amber-500',
}

const statusIcons: Record<NodeStatus, LucideIcon> = {
  online: CircleCheck,
  offline: CircleX,
  unknown: HelpCircle,
}

const statusVariants: Record<NodeStatus, 'success' | 'destructive' | 'warning'> = {
  online: 'success',
  offline: 'destructive',
  unknown: 'warning',
}

export default function NodeSelector() {
  const { user } = useAuth()
  const { activeNode, nodes, loading, activate } = useNode()
  const { success, error: notifyError } = useNotifications()
  const isAdmin = user?.role === 'admin'

  if (loading || !activeNode) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Server size={14} />
        <span>Узел...</span>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="flex items-center gap-2">
        <Server size={14} className="text-muted-foreground" />
        <span className="max-w-[140px] truncate text-xs font-medium">{activeNode.name}</span>
        <StatusDot status={activeNode.status} />
      </div>
    )
  }

  return (
    <Select
      value={String(activeNode.id)}
      onValueChange={(v) => {
        const id = Number(v)
        if (id !== activeNode.id) {
          const node = nodes.find((n) => n.id === id)
          void activate(id)
            .then(() => success(`Активный узел: ${node?.name ?? id}`))
            .catch((err) =>
              notifyError(err instanceof ApiError ? err.message : 'Ошибка активации узла'),
            )
        }
      }}
    >
      <SelectTrigger className="h-8 w-[200px] gap-2 text-xs">
        <Server size={14} className="shrink-0 text-muted-foreground" />
        <SelectValue placeholder="Выберите узел" />
      </SelectTrigger>
      <SelectContent>
        {nodes.map((node) => (
          <SelectItem key={node.id} value={String(node.id)}>
            <span className="flex items-center gap-2">
              <StatusDot status={node.status} />
              <span className="truncate">{node.name}</span>
              {node.is_local && (
                <Badge variant="outline" className="ml-1 h-4 px-1 text-[10px]">
                  локальный
                </Badge>
              )}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function StatusDot({ status }: { status: NodeStatus }) {
  return (
    <span
      className={cn('inline-flex h-2 w-2 shrink-0 rounded-full', statusColors[status])}
      title={statusLabels[status]}
    />
  )
}

export function NodeBadge({ name, status }: { name?: string | null; status?: NodeStatus }) {
  if (!name) return null
  return (
    <Badge variant="outline" className="gap-1.5 font-normal">
      <Activity size={12} />
      {name}
      {status && <StatusDot status={status} />}
    </Badge>
  )
}

export function NodeStatusBadge({ status, showLabel = true }: { status: NodeStatus; showLabel?: boolean }) {
  const Icon = statusIcons[status]
  return (
    <Badge variant={statusVariants[status]} className="gap-1 font-normal">
      <Icon size={12} />
      {showLabel && statusLabels[status]}
    </Badge>
  )
}
