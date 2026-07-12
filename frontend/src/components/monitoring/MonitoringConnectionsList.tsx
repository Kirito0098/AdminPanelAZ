import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowDown,
  ArrowDownToLine,
  ArrowUp,
  ArrowUpFromLine,
  Clock,
  MapPin,
  Unplug,
} from 'lucide-react'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import {
  getConnectionDisplayAddress,
  getConnectionGeoLabel,
  NodeScopeBadge,
} from '@/components/monitoring/ConnectionAddress'
import EmptyState from '@/components/ui/EmptyState'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime } from '@/lib/datetime'
import { formatBitrate, formatDurationShort, sessionDurationSeconds } from '@/lib/formatTraffic'
import { formatHaBadgeLabel, haBadgeTitle } from '@/lib/haBadgeLabel'
import { COL_CONNECTED_SINCE, COL_HANDSHAKE, COL_VPN_IP } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import type { HaNodePresence, OpenVpnClient, VpnConfigHaInfo, WireGuardPeer } from '@/types'
import type { NocSortKey } from '@/components/noc/NocConnectionFilters'

const PAGE_SIZE = 25

type SortKey = NocSortKey
type SortDir = 'asc' | 'desc'

export type MonitoringConnectionRow = {
  key: string
  protocol: 'openvpn' | 'wireguard'
  clientName: string
  online: boolean
  nodeName?: string | null
  activeNodeName?: string | null
  haNodes?: HaNodePresence[]
  ha?: VpnConfigHaInfo | null
  address: string
  geoLabel: string | null
  city?: string | null
  isp?: string | null
  vpnIp: string
  rx: number
  tx: number
  timeLabel: string
  sortTime: number
  durationSec: number | null
  rxBps: number | null
  txBps: number | null
  ratePending?: boolean
  interfaceName?: string
}

function parseTime(value?: string | null): number {
  if (!value) return 0
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? 0 : ms
}

function formatHandshake(value?: string | null) {
  if (!value) return '—'
  return formatDateTime(value)
}

export function buildMonitoringConnectionRows(
  openvpnClients: OpenVpnClient[],
  wireguardPeers: WireGuardPeer[],
  options: {
    showOpenVpn: boolean
    showWireGuard: boolean
    isWireGuardOnline: (peer: WireGuardPeer) => boolean
    rates?: Map<string, { rxBps: number | null; txBps: number | null }>
  },
): MonitoringConnectionRow[] {
  const rows: MonitoringConnectionRow[] = []
  const rates = options.rates

  if (options.showOpenVpn) {
    for (const client of openvpnClients) {
      const key = `ovpn-${client.ha?.sync_group_id ?? client.active_node_id ?? client.node_id ?? 'node'}-${client.common_name}-${client.real_address}`
      const rate = rates?.get(key)
      rows.push({
        key,
        protocol: 'openvpn',
        clientName: client.common_name,
        online: true,
        nodeName: client.active_node_name ?? client.node_name,
        activeNodeName: client.active_node_name ?? client.node_name,
        haNodes: client.ha_nodes,
        ha: client.ha,
        address: getConnectionDisplayAddress(client),
        geoLabel: getConnectionGeoLabel(client),
        city: client.city,
        isp: client.isp,
        vpnIp: client.virtual_address,
        rx: client.bytes_received,
        tx: client.bytes_sent,
        timeLabel: client.connected_since,
        sortTime: client.connected_since_ts
          ? client.connected_since_ts > 1e12
            ? client.connected_since_ts
            : client.connected_since_ts * 1000
          : parseTime(client.connected_since),
        durationSec: sessionDurationSeconds(client.connected_since_ts, client.connected_since),
        rxBps: rate?.rxBps ?? null,
        txBps: rate?.txBps ?? null,
      })
    }
  }

  if (options.showWireGuard) {
    for (const peer of wireguardPeers) {
      const online = options.isWireGuardOnline(peer)
      const key = `wg-${peer.ha?.sync_group_id ?? peer.active_node_id ?? peer.node_id ?? 'node'}-${peer.interface}-${peer.public_key}`
      const rate = rates?.get(key)
      rows.push({
        key,
        protocol: 'wireguard',
        clientName: peer.client_name || '—',
        online,
        nodeName: peer.active_node_name ?? peer.node_name,
        activeNodeName: peer.active_node_name ?? peer.node_name,
        haNodes: peer.ha_nodes,
        ha: peer.ha,
        address: getConnectionDisplayAddress(peer, 'endpoint'),
        geoLabel: getConnectionGeoLabel(peer),
        city: peer.city,
        isp: peer.isp,
        vpnIp: peer.allowed_ips || '—',
        rx: peer.transfer_rx,
        tx: peer.transfer_tx,
        timeLabel: formatHandshake(peer.latest_handshake),
        sortTime: parseTime(peer.latest_handshake),
        // WG has no reliable session start in v1
        durationSec: null,
        rxBps: rate?.rxBps ?? null,
        txBps: rate?.txBps ?? null,
        interfaceName: peer.interface,
      })
    }
  }

  return rows
}

type AddressBlockProps = {
  address: string
  geoLabel: string | null
  size?: 'sm' | 'md'
}

function AddressBlock({ address, geoLabel, size = 'md' }: AddressBlockProps) {
  return (
    <div className="min-w-0">
      <div className={cn('font-mono leading-snug text-foreground', size === 'md' ? 'text-sm' : 'text-xs')}>
        {address}
      </div>
      {geoLabel && (
        <div
          className={cn(
            'mt-1 inline-flex items-start gap-1.5 leading-snug text-foreground/75',
            size === 'md' ? 'text-xs' : 'text-[11px]',
          )}
        >
          <MapPin size={size === 'md' ? 13 : 11} className="mt-0.5 shrink-0 opacity-80" />
          <span>{geoLabel}</span>
        </div>
      )}
    </div>
  )
}

function NodeCell({ row }: { row: MonitoringConnectionRow }) {
  const nodeLabel = row.activeNodeName || row.nodeName || '—'
  const haTitle =
    row.haNodes && row.haNodes.length
      ? row.haNodes.map((n) => `${n.node_name}${n.online ? '' : ' (off)'}`).join(', ')
      : row.ha
        ? haBadgeTitle(row.ha)
        : undefined

  if (row.ha) {
    return (
      <div className="space-y-1">
        <div className="text-sm">{nodeLabel}</div>
        <Badge variant="outline" className="gap-1 text-xs" title={haTitle}>
          {formatHaBadgeLabel(row.ha)}
        </Badge>
      </div>
    )
  }
  return <NodeScopeBadge nodeName={row.nodeName} />
}

type MonitoringConnectionsListProps = {
  rows: MonitoringConnectionRow[]
  showNodeColumn: boolean
  sortKey?: SortKey
  sortDir?: SortDir
  onSortChange?: (key: SortKey, dir: SortDir) => void
  onDisconnectOpenVpn?: (clientName: string) => void
}

function ConnectionCard({
  row,
  showNodeColumn,
  onDisconnectOpenVpn,
}: {
  row: MonitoringConnectionRow
  showNodeColumn: boolean
  onDisconnectOpenVpn?: (clientName: string) => void
}) {
  return (
    <div
      className={cn(
        'rounded-xl border p-4 sm:p-5',
        row.online ? 'border-border/80 bg-card' : 'border-dashed bg-muted/20 opacity-90',
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <Link
            to={`/traffic?client=${encodeURIComponent(row.clientName)}`}
            className="truncate text-base font-semibold text-primary hover:underline"
          >
            {row.clientName}
          </Link>
          <p className="font-mono text-sm text-muted-foreground">{row.vpnIp}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {showNodeColumn && <NodeCell row={row} />}
          <Badge variant={row.protocol === 'openvpn' ? 'default' : 'secondary'} className="text-xs">
            {row.protocol === 'openvpn' ? 'OpenVPN' : 'WireGuard'}
          </Badge>
          <Badge variant={row.online ? 'success' : 'secondary'} className="text-xs">
            {row.online ? 'Онлайн' : 'Офлайн'}
          </Badge>
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Адрес</p>
          <AddressBlock address={row.address} geoLabel={row.geoLabel} />
        </div>
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Трафик</p>
          <p className="font-mono text-sm">
            <span className="inline-flex items-center gap-1">
              <ArrowDownToLine size={13} className="text-primary" />
              {formatBytes(row.rx)}
            </span>
            <span className="mx-2 text-muted-foreground">/</span>
            <span className="inline-flex items-center gap-1">
              <ArrowUpFromLine size={13} className="text-amber-500" />
              {formatBytes(row.tx)}
            </span>
          </p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            ↓ {formatBitrate(row.rxBps, { pending: row.ratePending })} · ↑{' '}
            {formatBitrate(row.txBps, { pending: row.ratePending })}
          </p>
        </div>
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {row.protocol === 'openvpn' ? COL_CONNECTED_SINCE : COL_HANDSHAKE}
          </p>
          <p className="inline-flex items-start gap-1.5 text-sm text-muted-foreground">
            <Clock size={14} className="mt-0.5 shrink-0" />
            <span>{row.timeLabel}</span>
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Длительность: {formatDurationShort(row.durationSec)}
          </p>
        </div>
      </div>
      {row.protocol === 'openvpn' && onDisconnectOpenVpn && (
        <div className="mt-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5 text-destructive"
            onClick={() => onDisconnectOpenVpn(row.clientName)}
          >
            <Unplug size={14} />
            Отключить
          </Button>
        </div>
      )}
    </div>
  )
}

function SortHeader({
  label,
  sortKey,
  active,
  dir,
  onSort,
  className,
}: {
  label: string
  sortKey: SortKey
  active: boolean
  dir: SortDir
  onSort: (key: SortKey) => void
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      className={cn(
        'inline-flex items-center gap-1 transition-colors hover:text-foreground',
        active ? 'text-foreground' : 'text-muted-foreground',
        className,
      )}
    >
      {label}
      {active && (dir === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
    </button>
  )
}

export default function MonitoringConnectionsList({
  rows,
  showNodeColumn,
  sortKey: controlledSortKey,
  sortDir: controlledSortDir,
  onSortChange,
  onDisconnectOpenVpn,
}: MonitoringConnectionsListProps) {
  const [localSortKey, setLocalSortKey] = useState<SortKey>('traffic')
  const [localSortDir, setLocalSortDir] = useState<SortDir>('desc')
  const [visible, setVisible] = useState(PAGE_SIZE)

  const sortKey = controlledSortKey ?? localSortKey
  const sortDir = controlledSortDir ?? localSortDir

  const handleSort = (key: SortKey) => {
    let nextDir: SortDir = key === 'client' ? 'asc' : 'desc'
    if (key === sortKey) {
      nextDir = sortDir === 'asc' ? 'desc' : 'asc'
    }
    if (onSortChange) {
      onSortChange(key, nextDir)
    } else {
      setLocalSortKey(key)
      setLocalSortDir(nextDir)
    }
    setVisible(PAGE_SIZE)
  }

  const sortedRows = useMemo(() => {
    const factor = sortDir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'client') cmp = a.clientName.localeCompare(b.clientName)
      else if (sortKey === 'traffic') cmp = a.rx + a.tx - (b.rx + b.tx)
      else if (sortKey === 'rate') {
        const aRate = (a.rxBps ?? -1) + (a.txBps ?? -1)
        const bRate = (b.rxBps ?? -1) + (b.txBps ?? -1)
        cmp = aRate - bRate
      } else if (sortKey === 'duration') {
        cmp = (a.durationSec ?? -1) - (b.durationSec ?? -1)
      } else cmp = a.sortTime - b.sortTime
      if (cmp === 0) cmp = a.clientName.localeCompare(b.clientName)
      return cmp * factor
    })
  }, [rows, sortKey, sortDir])

  const visibleRows = sortedRows.slice(0, visible)
  const hasMore = visibleRows.length < sortedRows.length

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={Clock}
        title="Нет записей"
        description="Измените фильтр или дождитесь подключений клиентов"
        className="py-8"
      />
    )
  }

  return (
    <>
      <div className="mb-3 flex items-center justify-between gap-2 text-xs text-muted-foreground lg:hidden">
        <span>
          Показано {visibleRows.length} из {sortedRows.length}
        </span>
        <div className="inline-flex gap-1">
          {(['traffic', 'rate', 'duration', 'time', 'client'] as SortKey[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => handleSort(key)}
              className={cn(
                'inline-flex items-center gap-1 rounded-md border px-2 py-1 transition-colors',
                sortKey === key ? 'border-primary/40 bg-primary/5 text-foreground' : 'hover:text-foreground',
              )}
            >
              {key === 'traffic'
                ? 'Трафик'
                : key === 'rate'
                  ? 'Mbps'
                  : key === 'duration'
                    ? 'Время'
                    : key === 'time'
                      ? 'Активность'
                      : 'Имя'}
              {sortKey === key &&
                (sortDir === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveDataView
        mobile={visibleRows.map((row) => (
          <ConnectionCard
            key={row.key}
            row={row}
            showNodeColumn={showNodeColumn}
            onDisconnectOpenVpn={onDisconnectOpenVpn}
          />
        ))}
        desktop={
          <Table className="min-w-[1280px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-[120px] text-xs uppercase tracking-wide">Протокол</TableHead>
                {showNodeColumn && <TableHead className="min-w-[120px]">Узел</TableHead>}
                <TableHead className="min-w-[160px]">
                  <SortHeader label="Клиент" sortKey="client" active={sortKey === 'client'} dir={sortDir} onSort={handleSort} />
                </TableHead>
                <TableHead className="min-w-[240px]">Адрес / локация</TableHead>
                <TableHead className="min-w-[140px]">{COL_VPN_IP}</TableHead>
                <TableHead className="min-w-[110px] text-right">
                  <SortHeader label="RX" sortKey="traffic" active={sortKey === 'traffic'} dir={sortDir} onSort={handleSort} className="justify-end" />
                </TableHead>
                <TableHead className="min-w-[110px] text-right">TX</TableHead>
                <TableHead className="min-w-[100px] text-right">
                  <SortHeader label="↓ Mbps" sortKey="rate" active={sortKey === 'rate'} dir={sortDir} onSort={handleSort} className="justify-end" />
                </TableHead>
                <TableHead className="min-w-[100px] text-right">↑ Mbps</TableHead>
                <TableHead className="min-w-[100px]">
                  <SortHeader label="Длительность" sortKey="duration" active={sortKey === 'duration'} dir={sortDir} onSort={handleSort} />
                </TableHead>
                <TableHead className="min-w-[160px]">
                  <SortHeader label="Активность" sortKey="time" active={sortKey === 'time'} dir={sortDir} onSort={handleSort} />
                </TableHead>
                <TableHead className="w-[100px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleRows.map((row) => (
                <TableRow
                  key={row.key}
                  className={cn('align-top', row.online && row.protocol === 'wireguard' && 'bg-emerald-500/5')}
                >
                  <TableCell>
                    <div className="flex flex-col gap-1.5">
                      <Badge variant={row.protocol === 'openvpn' ? 'default' : 'secondary'} className="w-fit text-xs">
                        {row.protocol === 'openvpn' ? 'OpenVPN' : 'WireGuard'}
                      </Badge>
                      <Badge variant={row.online ? 'success' : 'secondary'} className="w-fit text-xs">
                        {row.online ? 'Онлайн' : 'Офлайн'}
                      </Badge>
                    </div>
                  </TableCell>
                  {showNodeColumn && (
                    <TableCell className="text-sm">
                      <NodeCell row={row} />
                    </TableCell>
                  )}
                  <TableCell>
                    <div className="space-y-1">
                      <Link
                        to={`/traffic?client=${encodeURIComponent(row.clientName)}`}
                        className="text-sm font-semibold text-primary hover:underline"
                      >
                        {row.clientName}
                      </Link>
                      {row.interfaceName && (
                        <p className="font-mono text-xs text-muted-foreground">{row.interfaceName}</p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <AddressBlock address={row.address} geoLabel={row.geoLabel} />
                  </TableCell>
                  <TableCell className="font-mono text-sm">{row.vpnIp}</TableCell>
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    <span className="inline-flex items-center justify-end gap-1">
                      <ArrowDownToLine size={13} className="text-primary" />
                      {formatBytes(row.rx)}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    <span className="inline-flex items-center justify-end gap-1">
                      <ArrowUpFromLine size={13} className="text-amber-500" />
                      {formatBytes(row.tx)}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    {formatBitrate(row.rxBps, { pending: row.ratePending })}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm tabular-nums">
                    {formatBitrate(row.txBps, { pending: row.ratePending })}
                  </TableCell>
                  <TableCell className="text-sm tabular-nums">{formatDurationShort(row.durationSec)}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    <span className="inline-flex items-start gap-1.5">
                      <Clock size={14} className="mt-0.5 shrink-0" />
                      <span className="leading-snug">{row.timeLabel}</span>
                    </span>
                  </TableCell>
                  <TableCell>
                    {row.protocol === 'openvpn' && onDisconnectOpenVpn ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="gap-1 text-destructive"
                        onClick={() => onDisconnectOpenVpn(row.clientName)}
                        title="Отключить сессию OpenVPN"
                      >
                        <Unplug size={14} />
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        mobileClassName="space-y-3"
        desktopClassName="overflow-x-auto rounded-xl border"
      />

      {hasMore && (
        <div className="mt-4 flex items-center justify-center gap-3">
          <span className="text-xs text-muted-foreground">
            Показано {visibleRows.length} из {sortedRows.length}
          </span>
          <Button variant="outline" size="sm" onClick={() => setVisible((v) => v + PAGE_SIZE)}>
            Показать ещё {Math.min(PAGE_SIZE, sortedRows.length - visibleRows.length)}
          </Button>
        </div>
      )}
    </>
  )
}
