import { useMemo, useState } from 'react'
import { ChevronDown, ChevronsDownUp, ChevronsUpDown, Clock, User } from 'lucide-react'
import MonitoringConnectionsList, {
  type DeviceDisconnectTarget,
  type MonitoringConnectionRow,
} from '@/components/monitoring/MonitoringConnectionsList'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { groupConnectionsByOwner } from '@/lib/connectionUserGroups'
import { formatDateTime } from '@/lib/datetime'
import { formatBytes } from '@/lib/trafficFormat'
import { cn } from '@/lib/utils'

const PROTOCOL_LABELS: Record<string, string> = {
  openvpn: 'OpenVPN',
  wireguard: 'WireGuard',
  amneziawg2: 'AWG 2.0',
}

function usersLabel(count: number) {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return 'пользователь'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'пользователя'
  return 'пользователей'
}

function connectionsLabel(count: number) {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return 'подключение'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'подключения'
  return 'подключений'
}

type MonitoringUsersListProps = {
  rows: MonitoringConnectionRow[]
  showNodeColumn: boolean
  onDisconnectOpenVpn?: (clientName: string) => void
  onDisconnectDevice?: (target: DeviceDisconnectTarget, blockMinutes?: number) => void
}

/**
 * NOC connections grouped by the user who owns the config.
 *
 * A collapsed row shows the per-user totals (connections, online, traffic,
 * nodes); expanding reuses the regular connection list for that user, so
 * sorting, pagination and the disconnect action stay identical.
 */
export default function MonitoringUsersList({
  rows,
  showNodeColumn,
  onDisconnectOpenVpn,
  onDisconnectDevice,
}: MonitoringUsersListProps) {
  const groups = useMemo(() => groupConnectionsByOwner(rows), [rows])
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const allExpanded = groups.length > 0 && groups.every((group) => expanded.has(group.key))

  const toggle = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleAll = () => {
    setExpanded(allExpanded ? new Set() : new Set(groups.map((group) => group.key)))
  }

  if (groups.length === 0) return null

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {groups.length} {usersLabel(groups.length)} · {rows.length}{' '}
          {connectionsLabel(rows.length)}
        </p>
        <Button type="button" variant="ghost" size="sm" className="gap-1.5 text-xs" onClick={toggleAll}>
          {allExpanded ? <ChevronsDownUp size={14} /> : <ChevronsUpDown size={14} />}
          {allExpanded ? 'Свернуть все' : 'Развернуть все'}
        </Button>
      </div>

      {groups.map((group) => {
        const open = expanded.has(group.key)
        const lastActivity = group.lastActivity > 0 ? formatDateTime(new Date(group.lastActivity).toISOString()) : null
        return (
          <div key={group.key} className="overflow-hidden rounded-xl border border-border/80 bg-card">
            <button
              type="button"
              onClick={() => toggle(group.key)}
              aria-expanded={open}
              className={cn(
                'flex w-full flex-col gap-3 p-4 text-left transition-colors hover:bg-muted/40 sm:flex-row sm:items-center sm:justify-between',
                open && 'bg-primary/5',
              )}
            >
              <div className="flex min-w-0 items-start gap-3">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border bg-muted/60">
                  <User size={16} className={group.onlineCount > 0 ? 'text-primary' : 'text-muted-foreground'} />
                </span>
                <div className="min-w-0 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="truncate text-base font-semibold">{group.ownerName}</span>
                    <Badge variant={group.onlineCount > 0 ? 'success' : 'secondary'} className="text-[10px]">
                      {group.onlineCount > 0 ? 'Онлайн' : 'Офлайн'}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      {group.onlineCount}/{group.connectionsCount} {connectionsLabel(group.connectionsCount)}
                    </Badge>
                    {group.protocols.map((protocol) => (
                      <Badge key={protocol} variant="secondary" className="text-[10px]">
                        {PROTOCOL_LABELS[protocol] ?? protocol}
                      </Badge>
                    ))}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {group.nodes.length > 0 ? `Узлы: ${group.nodes.join(', ')}` : 'Узел не определён'}
                    {lastActivity ? ' · активность: ' : ''}
                    {lastActivity ? (
                      <span className="inline-flex items-center gap-1 align-middle">
                        <Clock size={11} className="shrink-0" />
                        {lastActivity}
                      </span>
                    ) : null}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-4 pl-11 sm:pl-0">
                <div className="text-right">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">RX / TX</p>
                  <p className="mono text-sm font-medium tabular-nums">
                    {formatBytes(group.rx)} / {formatBytes(group.tx)}
                  </p>
                </div>
                <ChevronDown
                  size={18}
                  className={cn('shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')}
                />
              </div>
            </button>
            {open && (
              <div className="border-t bg-muted/10 p-3 sm:p-4">
                <MonitoringConnectionsList
                  rows={group.rows}
                  showNodeColumn={showNodeColumn}
                  onDisconnectOpenVpn={onDisconnectOpenVpn}
                  onDisconnectDevice={onDisconnectDevice}
                />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
