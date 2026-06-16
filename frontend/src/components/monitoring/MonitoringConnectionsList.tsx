import { Link } from 'react-router-dom'
import { ArrowDownToLine, ArrowUpFromLine, Clock, MapPin } from 'lucide-react'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import {
  getConnectionDisplayAddress,
  getConnectionGeoLabel,
  NodeScopeBadge,
} from '@/components/monitoring/ConnectionAddress'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { OpenVpnClient, VpnConfigHaInfo, WireGuardPeer } from '@/types'

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
  interfaceName?: string
}

function formatHandshake(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU')
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
            <Badge variant="outline" className="gap-1 text-xs">
              HA: {row.ha.shared_domain} ({row.ha.node_count} узл.)
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

      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
            {row.protocol === 'openvpn' ? 'Подключён с' : 'Handshake'}
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

export default function MonitoringConnectionsList({ rows, showNodeColumn }: MonitoringConnectionsListProps) {
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
      <div className="space-y-3 xl:hidden">
        {rows.map((row) => (
          <ConnectionCard key={row.key} row={row} showNodeColumn={showNodeColumn} />
        ))}
      </div>

      <div className="hidden overflow-x-auto rounded-xl border xl:block">
        <Table className="min-w-[1080px]">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[120px] text-xs uppercase tracking-wide">Протокол</TableHead>
              {showNodeColumn && <TableHead className="min-w-[120px]">Узел</TableHead>}
              <TableHead className="min-w-[160px]">Клиент</TableHead>
              <TableHead className="min-w-[240px]">Адрес / локация</TableHead>
              <TableHead className="min-w-[140px]">VPN IP</TableHead>
              <TableHead className="min-w-[110px] text-right">RX</TableHead>
              <TableHead className="min-w-[110px] text-right">TX</TableHead>
              <TableHead className="min-w-[180px]">Активность</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
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
                      <Badge variant="outline" className="gap-1 text-xs">
                        HA: {row.ha.shared_domain} ({row.ha.node_count} узл.)
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
      </div>
    </>
  )
}
