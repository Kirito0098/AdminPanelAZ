import type { LucideIcon } from 'lucide-react'
import { Activity, CircleCheck, CircleX, HelpCircle, Layers, Server } from 'lucide-react'
import { useLocation } from 'react-router-dom'
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
import {
  buildHaSelectorOptions,
  getHaScopeDisplayLabel,
  isHaGroupScopePath,
  resolveHaSelectorValue,
  type HaSelectorOption,
} from '@/lib/haNodeScope'
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

export default function NodeSelector({ compact = false }: { compact?: boolean }) {
  const location = useLocation()
  const { user } = useAuth()
  const { activeNode, activeNodeHa, nodes, syncGroups, syncGroupsLoaded, loading, activate } = useNode()
  const { success, error: notifyError } = useNotifications()
  const isAdmin = user?.role === 'admin'
  const isHaScope = isHaGroupScopePath(location.pathname)
  const useHaSelector = isHaScope && syncGroupsLoaded && isAdmin

  const handleActivate = (id: number, label: string) => {
    if (id === activeNode?.id) return
    void activate(id)
      .then(() => success(`Активный узел: ${label}`))
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка активации узла'))
  }

  const triggerWidth = compact ? 'w-[130px]' : 'w-[200px]'
  const haTriggerWidth = compact ? 'w-[140px]' : 'w-[220px]'

  if (loading || !activeNode) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Server size={14} />
        {!compact && <span>Узел...</span>}
      </div>
    )
  }

  if (!isAdmin) {
    const label = getHaScopeDisplayLabel(activeNodeHa, activeNode, isHaScope)
    return (
      <div className="flex items-center gap-2">
        {isHaScope && activeNodeHa ? (
          <Layers size={14} className="text-muted-foreground" />
        ) : (
          <Server size={14} className="text-muted-foreground" />
        )}
        <span className={cn('truncate text-xs font-medium', compact ? 'max-w-[90px]' : 'max-w-[140px]')}>
          {label}
        </span>
        {isHaScope && activeNodeHa ? (
          <Badge variant="outline" className="h-4 px-1 text-[10px]">
            HA
          </Badge>
        ) : (
          <StatusDot status={activeNode.status} />
        )}
      </div>
    )
  }

  if (useHaSelector) {
    const options = buildHaSelectorOptions(nodes, syncGroups)
    const currentValue = resolveHaSelectorValue(activeNode, activeNodeHa, syncGroups)
    const activeGroup =
      activeNodeHa ??
      (() => {
        const group = syncGroups.find((item) => `group:${item.id}` === currentValue)
        if (!group) return null
        return {
          group_name: group.name,
          shared_domain: group.shared_domain,
        }
      })()

    return (
      <Select
        value={currentValue}
        onValueChange={(value) => {
          if (value === currentValue) return
          if (value.startsWith('group:')) {
            const groupId = Number(value.slice('group:'.length))
            const group = syncGroups.find((item) => item.id === groupId)
            if (!group) return
            handleActivate(group.primary_node_id, group.name)
            return
          }
          if (value.startsWith('node:')) {
            const nodeId = Number(value.slice('node:'.length))
            const node = nodes.find((item) => item.id === nodeId)
            handleActivate(nodeId, node?.name ?? String(nodeId))
          }
        }}
      >
        <SelectTrigger className={cn('h-8 gap-2 text-xs', haTriggerWidth)}>
          <Layers size={14} className="shrink-0 text-muted-foreground" />
          <SelectValue placeholder="Выберите HA-группу">
            {activeGroup ? (
              <span className="flex min-w-0 items-center gap-2">
                <span className="truncate">{activeGroup.group_name}</span>
                {!compact && (
                  <Badge variant="outline" className="h-4 max-w-[96px] truncate px-1 text-[10px] font-normal">
                    {activeGroup.shared_domain}
                  </Badge>
                )}
              </span>
            ) : (
              <span className="truncate">{activeNode.name}</span>
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.key} value={option.key}>
              <HaSelectorOptionLabel option={option} />
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }

  return (
    <Select
      value={String(activeNode.id)}
      onValueChange={(value) => {
        const id = Number(value)
        const node = nodes.find((item) => item.id === id)
        handleActivate(id, node?.name ?? value)
      }}
    >
      <SelectTrigger className={cn('h-8 gap-2 text-xs', triggerWidth)}>
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

function HaSelectorOptionLabel({ option }: { option: HaSelectorOption }) {
  if (option.type === 'group') {
    return (
      <span className="flex items-center gap-2">
        <StatusDot status={option.primaryStatus} />
        <span className="truncate">{option.label}</span>
        <Badge variant="outline" className="ml-1 h-4 max-w-[120px] truncate px-1 text-[10px]">
          {option.sharedDomain}
        </Badge>
      </span>
    )
  }

  return (
    <span className="flex items-center gap-2">
      <StatusDot status={option.status} />
      <span className="truncate">{option.label}</span>
      {option.isLocal && (
        <Badge variant="outline" className="ml-1 h-4 px-1 text-[10px]">
          локальный
        </Badge>
      )}
    </span>
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
    <Badge variant={statusVariants[status]} className="gap-1 whitespace-nowrap font-normal">
      <Icon size={12} className="shrink-0" />
      {showLabel && statusLabels[status]}
    </Badge>
  )
}
