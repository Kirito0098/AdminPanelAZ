import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDown, ArrowDownToLine, ArrowUp, ArrowUpFromLine, Clock, MapPin } from 'lucide-react'
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
import { formatHaBadgeLabel, haBadgeTitle } from '@/lib/haBadgeLabel'
import { COL_CONNECTED_SINCE, COL_HANDSHAKE, COL_VPN_IP } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import type { OpenVpnClient, VpnConfigHaInfo, WireGuardPeer } from '@/types'

const PAGE_SIZE = 25

type SortKey = 'client' | 'traffic' | 'time'
type SortDir = 'asc' | 'desc'

export type MonitoringConnectionRow = {
  key: string
  protocol: 'openvpn' | 'wireguard'
  clientName: string
  online: boolean
  nodeName?: string | null
  ha?: VpnConfigHaInfo | null
  address: string
  geoLabel: string | null
  vpnIp: string
  rx: number
  tx: number
  timeLabel: string
  sortTime: number
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
  },
): MonitoringConnectionRow[] {
  const rows: MonitoringConnectionRow[] = []

  if (options.showOpenVpn) {
    for (const client of openvpnClients) {
      rows.push({
        key: `ovpn-${client.ha?.sync_group_id ?? client.node_id ?? 'node'}-${client.common_name}-${client.real_address}`,
        protocol: 'openvpn',
        clientName: client.common_name,
        online: true,
        nodeName: client.node_name,
        ha: client.ha,
        address: getConnectionDisplayAddress(client),
        geoLabel: getConnectionGeoLabel(client),
        vpnIp: client.virtual_address,
        rx: client.bytes_received,
        tx: client.bytes_sent,
        timeLabel: client.connected_since,
        sortTime: parseTime(client.connected_since),
      })
    }
  }

  if (options.showWireGuard) {
    for (const peer of wireguardPeers) {
      const online = options.isWireGuardOnline(peer)
      rows.push({
        key: `wg-${peer.ha?.sync_group_id ?? peer.node_id ?? 'node'}-${peer.interface}-${peer.public_key}`,
        protocol: 'wireguard',
        clientName: peer.client_name || '—',
        online,
        nodeName: peer.node_name,
        ha: peer.ha,
        address: getConnectionDisplayAddress(peer, 'endpoint'),
        geoLabel: getConnectionGeoLabel(peer),
        vpnIp: peer.allowed_ips || '—',
        rx: peer.transfer_rx,
        tx: peer.transfer_tx,
        timeLabel: formatHandshake(peer.latest_handshake),
        sortTime: parseTime(peer.latest_handshake),
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

type MonitoringConnectionsListProps = {
  rows: MonitoringConnectionRow[]
  showNodeColumn: boolean
}

function ConnectionCard({ row, showNodeColumn }: { row: MonitoringConnectionRow; showNodeColumn: boolean }) {
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
          {row.ha ? (
            <Badge variant="outline" className="gap-1 text-xs" title={haBadgeTitle(row.ha)}>
              {formatHaBadgeLabel(row.ha)}
            </Badge>
          ) : (
            showNodeColumn && <NodeScopeBadge nodeName={row.nodeName} />
          )}
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
        </div>
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {row.protocol === 'openvpn' ? COL_CONNECTED_SINCE : COL_HANDSHAKE}
          </p>
          <p className="inline-flex items-start gap-1.5 text-sm text-muted-foreground">
            <Clock size={14} className="mt-0.5 shrink-0" />
            <span>{row.timeLabel}</span>
          </p>
        </div>
      </div>
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
      {active &&
        (dir === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
    </button>
  )
}

export default function MonitoringConnectionsList({ rows, showNodeColumn }: MonitoringConnectionsListProps) {
  const [sortKey, setSortKey] = useState<SortKey>('traffic')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [visible, setVisible] = useState(PAGE_SIZE)

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'client' ? 'asc' : 'desc')
    }
    setVisible(PAGE_SIZE)
  }

  const sortedRows = useMemo(() => {
    const factor = sortDir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'client') cmp = a.clientName.localeCompare(b.clientName)
      else if (sortKey === 'traffic') cmp = a.rx + a.tx - (b.rx + b.tx)
      else cmp = a.sortTime - b.sortTime
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
          {(['traffic', 'time', 'client'] as SortKey[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => handleSort(key)}
              className={cn(
                'inline-flex items-center gap-1 rounded-md border px-2 py-1 transition-colors',
                sortKey === key ? 'border-primary/40 bg-primary/5 text-foreground' : 'hover:text-foreground',
              )}
            >
              {key === 'traffic' ? 'Трафик' : key === 'time' ? 'Время' : 'Имя'}
              {sortKey === key &&
                (sortDir === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveDataView
        mobile={visibleRows.map((row) => (
          <ConnectionCard key={row.key} row={row} showNodeColumn={showNodeColumn} />
        ))}
        desktop={
          <Table className="min-w-[1080px]">
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
                <TableHead className="min-w-[180px]">
                  <SortHeader label="Активность" sortKey="time" active={sortKey === 'time'} dir={sortDir} onSort={handleSort} />
                </TableHead>
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
                      {row.ha ? (
                        <Badge variant="outline" className="gap-1 text-xs" title={haBadgeTitle(row.ha)}>
                          {formatHaBadgeLabel(row.ha)}
                        </Badge>
                      ) : (
                        row.nodeName || '—'
                      )}
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
                  <TableCell className="text-sm text-muted-foreground">
                    <span className="inline-flex items-start gap-1.5">
                      <Clock size={14} className="mt-0.5 shrink-0" />
                      <span className="leading-snug">{row.timeLabel}</span>
                    </span>
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
