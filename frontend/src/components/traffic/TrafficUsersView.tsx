import { Fragment, useMemo, useState, type ReactNode } from 'react'
import { ChevronDown, Clock, User } from 'lucide-react'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import { Badge } from '@/components/ui/badge'
import { PercentBar } from '@/components/ui/percent-bar'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime } from '@/lib/datetime'
import { formatBytes, protocolBadgeVariant, protocolLabel } from '@/lib/trafficFormat'
import type { TrafficUserGroup } from '@/lib/userGrouping'
import { cn } from '@/lib/utils'
import type { TrafficClientRow } from '@/types'

type TrafficUsersViewProps = {
  groups: TrafficUserGroup[]
  /** Largest row total in the current filter — the 100% reference for share bars. */
  maxTotalBytes: number
  periodLabel?: string
  selectedClient: string
  selectedProtocol: string
  onToggleClient: (clientName: string, protocol: string) => void
  renderDetails: (row: TrafficClientRow) => ReactNode
}

function formatLastSeen(value?: string | null) {
  return value ? formatDateTime(value) : '—'
}

function ShareBar({ value, max }: { value: number; max: number }) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <PercentBar value={value} max={max} className="h-1.5 min-w-0 flex-1" />
      <span className="mono w-10 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground">
        {max > 0 ? Math.min((value / max) * 100, 100).toFixed(0) : '0'}%
      </span>
    </div>
  )
}

function UserSummary({ group, open }: { group: TrafficUserGroup; open: boolean }) {
  return (
    <>
      <div className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border bg-muted/60">
          <User size={16} className={group.isActive ? 'text-primary' : 'text-muted-foreground'} />
        </span>
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-base font-semibold">{group.username}</span>
            <Badge variant={group.isActive ? 'success' : 'secondary'} className="text-[10px]">
              {group.isActive ? 'Онлайн' : 'Офлайн'}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              {group.activeConfigsCount}/{group.configsCount} конфигов
            </Badge>
            {group.protocols.map((protocol) => (
              <Badge key={protocol} variant={protocolBadgeVariant(protocol)} className="text-[10px]">
                {protocolLabel(protocol)}
              </Badge>
            ))}
          </div>
          <p className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Clock size={11} className="shrink-0" />
            {formatLastSeen(group.lastSeenAt)}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-4 pl-11 sm:pl-0">
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Всего</p>
          <p className="mono text-sm font-medium tabular-nums">{formatBytes(group.totalBytes)}</p>
        </div>
        <ChevronDown
          size={18}
          className={cn('shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')}
        />
      </div>
    </>
  )
}

/**
 * Traffic rows grouped by the user who owns the configs.
 *
 * Groups are collapsed by default and show per-user totals; expanding reveals
 * the individual config rows. Selecting a config still opens the usual chart
 * and policy details through ``renderDetails``.
 */
export default function TrafficUsersView({
  groups,
  maxTotalBytes,
  periodLabel,
  selectedClient,
  selectedProtocol,
  onToggleClient,
  renderDetails,
}: TrafficUsersViewProps) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const selectedGroupKey = useMemo(
    () =>
      groups.find((group) =>
        group.rows.some(
          (row) => row.common_name === selectedClient && row.protocol_type === selectedProtocol,
        ),
      )?.key ?? null,
    [groups, selectedClient, selectedProtocol],
  )

  const isGroupOpen = (group: TrafficUserGroup) =>
    expanded.has(group.key) || group.key === selectedGroupKey

  const toggleGroup = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const isRowSelected = (row: TrafficClientRow) =>
    row.common_name === selectedClient && row.protocol_type === selectedProtocol

  return (
    <ResponsiveDataView
      mobile={groups.map((group) => {
        const open = isGroupOpen(group)
        return (
          <div
            key={group.key}
            className={cn(
              'overflow-hidden rounded-lg border transition-colors',
              open && 'border-primary/50',
            )}
          >
            <button
              type="button"
              onClick={() => toggleGroup(group.key)}
              aria-expanded={open}
              className={cn(
                'flex w-full flex-col gap-3 p-4 text-left transition-colors hover:bg-muted/40',
                open && 'bg-primary/5',
              )}
            >
              <UserSummary group={group} open={open} />
            </button>
            {open && (
              <div className="border-t bg-muted/10">
                {group.rows.map((row) => {
                  const rowSelected = isRowSelected(row)
                  return (
                    <div key={`${row.common_name}-${row.protocol_type}`} className="border-b last:border-b-0">
                      <button
                        type="button"
                        onClick={() => onToggleClient(row.common_name, row.protocol_type)}
                        aria-expanded={rowSelected}
                        className={cn(
                          'flex w-full items-center justify-between gap-3 p-3 text-left transition-colors hover:bg-muted/40',
                          rowSelected && 'bg-primary/5',
                        )}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{row.common_name}</p>
                          <Badge variant={protocolBadgeVariant(row.protocol_type)} className="mt-1 text-[10px]">
                            {protocolLabel(row.protocol_type)}
                          </Badge>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="mono text-sm tabular-nums">{formatBytes(row.total_bytes)}</p>
                          <p className="text-[10px] text-muted-foreground">
                            за период: {formatBytes(row.traffic_period)}
                          </p>
                        </div>
                      </button>
                      {rowSelected && (
                        <div className="border-t bg-card p-3">{renderDetails(row)}</div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
      desktop={
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>Пользователь</TableHead>
              <TableHead>Протоколы</TableHead>
              <TableHead className="text-right">RX</TableHead>
              <TableHead className="text-right">TX</TableHead>
              <TableHead className="text-right">Всего</TableHead>
              <TableHead className="min-w-[8rem]">Доля</TableHead>
              <TableHead className="text-right">
                За период
                <span className="block text-[10px] font-normal text-muted-foreground">
                  {periodLabel ?? ''}
                </span>
              </TableHead>
              <TableHead>Последний раз</TableHead>
              <TableHead>Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {groups.map((group) => (
              <UserGroupRows
                key={group.key}
                group={group}
                open={isGroupOpen(group)}
                maxTotalBytes={maxTotalBytes}
                isRowSelected={isRowSelected}
                onToggleGroup={() => toggleGroup(group.key)}
                onToggleClient={onToggleClient}
                renderDetails={renderDetails}
              />
            ))}
          </TableBody>
        </Table>
      }
      mobileClassName="space-y-3"
      desktopClassName="overflow-x-auto rounded-md border"
    />
  )
}

function UserGroupRows({
  group,
  open,
  maxTotalBytes,
  isRowSelected,
  onToggleGroup,
  onToggleClient,
  renderDetails,
}: {
  group: TrafficUserGroup
  open: boolean
  maxTotalBytes: number
  isRowSelected: (row: TrafficClientRow) => boolean
  onToggleGroup: () => void
  onToggleClient: (clientName: string, protocol: string) => void
  renderDetails: (row: TrafficClientRow) => ReactNode
}) {
  return (
    <>
      <TableRow
        className={cn('cursor-pointer hover:bg-muted/50', open && 'bg-primary/5')}
        onClick={onToggleGroup}
      >
        <TableCell className="w-8 px-2">
          <ChevronDown
            size={16}
            className={cn('text-muted-foreground transition-transform', open && 'rotate-180')}
          />
        </TableCell>
        <TableCell>
          <div className="font-medium">{group.username}</div>
          <div className="text-[10px] text-muted-foreground">
            {group.activeConfigsCount}/{group.configsCount} конфигов
          </div>
        </TableCell>
        <TableCell>
          <div className="flex flex-wrap gap-1">
            {group.protocols.map((protocol) => (
              <Badge key={protocol} variant={protocolBadgeVariant(protocol)} className="text-[10px]">
                {protocolLabel(protocol)}
              </Badge>
            ))}
          </div>
        </TableCell>
        <TableCell className="whitespace-nowrap text-right font-mono text-xs">
          {formatBytes(group.totalReceived)}
        </TableCell>
        <TableCell className="whitespace-nowrap text-right font-mono text-xs">
          {formatBytes(group.totalSent)}
        </TableCell>
        <TableCell className="whitespace-nowrap text-right font-mono text-xs font-medium">
          {formatBytes(group.totalBytes)}
        </TableCell>
        <TableCell>
          <ShareBar value={group.totalBytes} max={maxTotalBytes} />
        </TableCell>
        <TableCell className="whitespace-nowrap text-right font-mono text-xs">
          {formatBytes(group.trafficPeriod)}
        </TableCell>
        <TableCell className="text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Clock size={12} className="shrink-0" />
            {formatLastSeen(group.lastSeenAt)}
          </span>
        </TableCell>
        <TableCell>
          <Badge variant={group.isActive ? 'success' : 'secondary'} className="text-[10px]">
            {group.isActive ? 'Онлайн' : 'Офлайн'}
          </Badge>
        </TableCell>
      </TableRow>
      {open &&
        group.rows.map((row) => {
          const rowSelected = isRowSelected(row)
          return (
            <Fragment key={`${row.common_name}-${row.protocol_type}`}>
              <TableRow
                className={cn('cursor-pointer hover:bg-muted/50', rowSelected && 'bg-primary/5')}
                onClick={() => onToggleClient(row.common_name, row.protocol_type)}
              >
                <TableCell className="w-8 px-2">
                  <ChevronDown
                    size={14}
                    className={cn(
                      'text-muted-foreground transition-transform',
                      rowSelected && 'rotate-180',
                    )}
                  />
                </TableCell>
                <TableCell className="pl-6 text-sm">{row.common_name}</TableCell>
                <TableCell>
                  <Badge variant={protocolBadgeVariant(row.protocol_type)} className="text-[10px]">
                    {protocolLabel(row.protocol_type)}
                  </Badge>
                </TableCell>
                <TableCell className="whitespace-nowrap text-right font-mono text-xs">
                  {formatBytes(row.total_received)}
                </TableCell>
                <TableCell className="whitespace-nowrap text-right font-mono text-xs">
                  {formatBytes(row.total_sent)}
                </TableCell>
                <TableCell className="whitespace-nowrap text-right font-mono text-xs font-medium">
                  {formatBytes(row.total_bytes)}
                </TableCell>
                <TableCell>
                  <ShareBar value={row.total_bytes} max={maxTotalBytes} />
                </TableCell>
                <TableCell className="whitespace-nowrap text-right font-mono text-xs">
                  {formatBytes(row.traffic_period)}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Clock size={12} className="shrink-0" />
                    {formatLastSeen(row.last_seen_at)}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge variant={row.is_active ? 'success' : 'secondary'} className="text-[10px]">
                    {row.is_active ? 'Онлайн' : 'Офлайн'}
                  </Badge>
                </TableCell>
              </TableRow>
              {rowSelected && (
                <TableRow className="bg-muted/20 hover:bg-muted/20">
                  <TableCell colSpan={10} className="p-0">
                    <div className="border-t border-primary/30 p-3">{renderDetails(row)}</div>
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          )
        })}
    </>
  )
}

