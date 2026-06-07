import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  ArrowDownToLine,
  ArrowUpFromLine,
  Clock,
  Cpu,
  Globe,
  Hash,
  LayoutDashboard,
  Loader2,
  Radio,
  Search,
  Server,
  Users,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { ApiError, getMonitoring, getResourceHistory } from '@/api/client'
import MonitoringCharts, { formatBytes, totalTraffic } from '@/components/monitoring/MonitoringCharts'
import PanelResourceHistoryCharts from '@/components/monitoring/PanelResourceHistoryCharts'
import ResourceHistoryCharts from '@/components/monitoring/ResourceHistoryCharts'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import ServiceMatrix from '@/components/noc/ServiceMatrix'
import { NodeBadge } from '@/components/NodeSelector'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { cn } from '@/lib/utils'
import type { MonitoringOverview, OpenVpnClient, ResourceHistory, WireGuardPeer } from '@/types'

const REFRESH_INTERVAL = 30

type ProtocolFilter = 'all' | 'openvpn' | 'wireguard'

function dataSourceLabel(source?: string) {
  if (source === 'management_socket') return 'Management socket'
  if (source === 'status_log') return 'Status-логи'
  return 'Нет данных'
}

function dataSourceVariant(source?: string): 'default' | 'secondary' | 'outline' {
  if (source === 'management_socket') return 'default'
  if (source === 'status_log') return 'secondary'
  return 'outline'
}

function isWireGuardOnline(peer: WireGuardPeer) {
  return Boolean(peer.latest_handshake)
}

function formatHandshake(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU')
}

type SummaryCardProps = {
  label: string
  value: string
  icon: typeof Users
  sub?: string
  accent?: string
}

function SummaryCard({ label, value, icon: Icon, sub, accent }: SummaryCardProps) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
          <div className={cn('rounded-md bg-muted p-2', accent ?? 'text-muted-foreground')}>
            <Icon size={16} />
          </div>
        </div>
        <p className="mono mt-2 text-2xl font-bold tracking-tight tabular-nums">{value}</p>
        {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  )
}

type OpenVpnClientCardProps = {
  client: OpenVpnClient
}

function OpenVpnClientCard({ client }: OpenVpnClientCardProps) {
  return (
    <div className="rounded-lg border p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium">{client.common_name}</p>
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">{client.virtual_address}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="default" className="text-[10px]">
            OVPN
          </Badge>
          <Badge variant="success" className="text-[10px]">
            Онлайн
          </Badge>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-muted-foreground">Real IP</p>
          <p className="font-mono">{client.real_address}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Подключён с</p>
          <p className="inline-flex items-center gap-1">
            <Clock size={12} className="shrink-0 text-muted-foreground" />
            {client.connected_since}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">RX</p>
          <p className="font-mono">{formatBytes(client.bytes_received)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">TX</p>
          <p className="font-mono">{formatBytes(client.bytes_sent)}</p>
        </div>
      </div>
    </div>
  )
}

type WireGuardPeerCardProps = {
  peer: WireGuardPeer
}

function WireGuardPeerCard({ peer }: WireGuardPeerCardProps) {
  const online = isWireGuardOnline(peer)
  return (
    <div className={cn('rounded-lg border p-4', online && 'border-emerald-500/20 bg-emerald-500/5')}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium">{peer.client_name || '—'}</p>
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">{peer.interface}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary" className="text-[10px]">
            WG
          </Badge>
          <Badge variant={online ? 'success' : 'secondary'} className="text-[10px]">
            {online ? 'Онлайн' : 'Офлайн'}
          </Badge>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-muted-foreground">Endpoint</p>
          <p className="font-mono">{peer.endpoint || '—'}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Allowed IPs</p>
          <p className="font-mono">{peer.allowed_ips || '—'}</p>
        </div>
        <div>
          <p className="text-muted-foreground">RX / TX</p>
          <p className="font-mono">
            {formatBytes(peer.transfer_rx)} / {formatBytes(peer.transfer_tx)}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Handshake</p>
          <p className="inline-flex items-center gap-1">
            <Clock size={12} className="shrink-0 text-muted-foreground" />
            {formatHandshake(peer.latest_handshake)}
          </p>
        </div>
      </div>
    </div>
  )
}

export default function MonitoringPage() {
  const { user } = useAuth()
  const { activeNode } = useNode()
  const isAdmin = user?.role === 'admin'
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal } = useProgress()
  const [data, setData] = useState<MonitoringOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const [search, setSearch] = useState('')
  const [protocolFilter, setProtocolFilter] = useState<ProtocolFilter>('all')
  const [resourcePeriod, setResourcePeriod] = useState<'1d' | '7d' | '30d'>('1d')
  const [panelResourcePeriod, setPanelResourcePeriod] = useState<'1d' | '7d' | '30d'>('1d')
  const [resourceHistory, setResourceHistory] = useState<ResourceHistory | null>(null)
  const [resourceLoading, setResourceLoading] = useState(false)
  const loadRef = useRef<(opts?: { initial?: boolean; manual?: boolean }) => Promise<void>>()

  const load = useCallback(
    async (opts: { initial?: boolean; manual?: boolean } = {}) => {
      const { initial = false, manual = false } = opts
      if (initial) {
        setLoading(true)
        startGlobal()
      } else if (manual) {
        setRefreshing(true)
      }
      try {
        setData(await getMonitoring())
        setLoadError(null)
        if (manual) success('Данные мониторинга обновлены')
        setCountdown(REFRESH_INTERVAL)
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Ошибка загрузки мониторинга'
        setLoadError(message)
        notifyError(message)
      } finally {
        setLoading(false)
        setRefreshing(false)
        if (initial) doneGlobal()
      }
    },
    [startGlobal, doneGlobal, success, notifyError],
  )

  loadRef.current = load

  const loadResourceHistory = useCallback(
    async (period: '1d' | '7d' | '30d') => {
      setResourceLoading(true)
      try {
        setResourceHistory(await getResourceHistory(period))
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Ошибка загрузки истории ресурсов'
        notifyError(message)
      } finally {
        setResourceLoading(false)
      }
    },
    [notifyError],
  )

  useEffect(() => {
    load({ initial: true })
  }, [load, activeNode?.id])

  useEffect(() => {
    loadResourceHistory(resourcePeriod)
  }, [loadResourceHistory, activeNode?.id, resourcePeriod])

  useEffect(() => {
    if (!autoRefresh) return

    const tick = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          loadRef.current?.()
          return REFRESH_INTERVAL
        }
        return c - 1
      })
    }, 1000)

    return () => clearInterval(tick)
  }, [autoRefresh])

  const nodeOffline = activeNode?.status === 'offline'
  const nodeUnknown = activeNode?.status === 'unknown'

  const openvpnClients = data?.openvpn_clients ?? []
  const wireguardPeers = data?.wireguard_peers ?? []
  const wgActive = wireguardPeers.filter(isWireGuardOnline).length
  const totalConnections = openvpnClients.length + wgActive
  const activeServices = data?.services.filter((s) => s.active).length ?? 0
  const totalServices = data?.services.length ?? 0

  const searchQuery = search.trim().toLowerCase()

  const filteredOpenVpn = useMemo(() => {
    if (!searchQuery) return openvpnClients
    return openvpnClients.filter(
      (c) =>
        c.common_name.toLowerCase().includes(searchQuery) ||
        c.real_address.toLowerCase().includes(searchQuery) ||
        c.virtual_address.toLowerCase().includes(searchQuery),
    )
  }, [openvpnClients, searchQuery])

  const filteredWireGuard = useMemo(() => {
    if (!searchQuery) return wireguardPeers
    return wireguardPeers.filter((p) => {
      const name = (p.client_name ?? '').toLowerCase()
      return (
        name.includes(searchQuery) ||
        (p.endpoint ?? '').toLowerCase().includes(searchQuery) ||
        (p.allowed_ips ?? '').toLowerCase().includes(searchQuery) ||
        p.interface.toLowerCase().includes(searchQuery) ||
        p.public_key.toLowerCase().includes(searchQuery)
      )
    })
  }, [wireguardPeers, searchQuery])

  const showOpenVpn = protocolFilter === 'all' || protocolFilter === 'openvpn'
  const showWireGuard = protocolFilter === 'all' || protocolFilter === 'wireguard'
  const hasFilteredClients =
    (showOpenVpn ? filteredOpenVpn.length : 0) + (showWireGuard ? filteredWireGuard.length : 0) > 0

  const handleRefresh = () => {
    load({ manual: true })
    loadResourceHistory(resourcePeriod)
  }

  if (loading && !data) {
    return <Spinner label="Загрузка NOC мониторинга..." className="py-16" />
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Radio size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold tracking-tight">NOC Мониторинг</h2>
              <NodeBadge name={activeNode?.name ?? data?.node_name} status={activeNode?.status} />
            </div>
            <p className="text-sm text-muted-foreground">
              Активные VPN-подключения OpenVPN и WireGuard в реальном времени
              {data?.timestamp && (
                <> · обновлено {new Date(data.timestamp).toLocaleString('ru-RU')}</>
              )}
            </p>
          </div>
        </div>
        <AutoRefreshControl
          enabled={autoRefresh}
          onToggle={() => setAutoRefresh((v) => !v)}
          countdown={countdown}
          intervalSec={REFRESH_INTERVAL}
          refreshing={refreshing}
          onManualRefresh={handleRefresh}
        />
      </div>

      <SettingsAlert variant="info" title="Данные активного узла">
        Мониторинг собирается с <strong>{activeNode?.name ?? data?.node_name ?? 'активного узла'}</strong>
        {activeNode?.is_local ? ' (локальный controller)' : ' (удалённый node agent)'}.
        Автообновление каждые {REFRESH_INTERVAL} с. Переключите узел в шапке или на странице «Узлы».
      </SettingsAlert>

      {nodeOffline && (
        <SettingsAlert variant="warning" title="Узел офлайн">
          Активный узел недоступен. Данные подключений могут быть устаревшими или отсутствовать.
          Проверьте связь с node agent и повторите обновление.
        </SettingsAlert>
      )}

      {nodeUnknown && !nodeOffline && (
        <SettingsAlert variant="warning" title="Статус узла неизвестен">
          Связь с узлом не подтверждена. Запустите проверку здоровья на странице «Узлы».
        </SettingsAlert>
      )}

      <InlineProgressBar active={refreshing} label="Обновление данных мониторинга..." />

      {loadError && !data ? (
        <Card>
          <CardContent>
            <EmptyState
              icon={WifiOff}
              title="Мониторинг недоступен"
              description={loadError}
              action={
                <Button onClick={handleRefresh} disabled={refreshing}>
                  {refreshing ? <Loader2 size={16} className="animate-spin" /> : <Activity size={16} />}
                  Повторить
                </Button>
              }
              className="py-8"
            />
          </CardContent>
        </Card>
      ) : (
        data && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={dataSourceVariant(data?.openvpn_data_source)}>
                Источник OVPN: {dataSourceLabel(data?.openvpn_data_source)}
              </Badge>
              {data?.server_ip && (
                <Badge variant="outline" className="gap-1">
                  <Globe size={10} />
                  {data.server_ip}
                </Badge>
              )}
              <Badge variant="outline" className="gap-1">
                <Hash size={10} />
                Службы: {activeServices}/{totalServices}
              </Badge>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <SummaryCard
                label="OpenVPN онлайн"
                value={String(openvpnClients.length)}
                icon={Wifi}
                accent="text-primary"
                sub="активных сессий"
              />
              <SummaryCard
                label="WireGuard онлайн"
                value={String(wgActive)}
                icon={Radio}
                accent="text-emerald-500"
                sub={`из ${wireguardPeers.length} пиров`}
              />
              <SummaryCard
                label="Всего подключено"
                value={String(totalConnections)}
                icon={Users}
                sub={`OVPN ${openvpnClients.length} · WG ${wgActive}`}
              />
              <SummaryCard
                label="Трафик сессий"
                value={formatBytes(totalTraffic(data))}
                icon={Activity}
                sub={`RX ${formatBytes(
                  openvpnClients.reduce((s, c) => s + c.bytes_received, 0) +
                    wireguardPeers.reduce((s, p) => s + p.transfer_rx, 0),
                )} · TX ${formatBytes(
                  openvpnClients.reduce((s, c) => s + c.bytes_sent, 0) +
                    wireguardPeers.reduce((s, p) => s + p.transfer_tx, 0),
                )}`}
              />
            </div>

            <MonitoringCharts data={data} />

            <Tabs defaultValue="connections">
              <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1">
                <TabsTrigger value="connections" className="gap-1.5">
                  <Wifi size={14} />
                  Подключения
                  {totalConnections > 0 && (
                    <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                      {totalConnections}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="services" className="gap-1.5">
                  <Server size={14} />
                  Службы
                  {totalServices > 0 && (
                    <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                      {activeServices}/{totalServices}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="resources" className="gap-1.5">
                  <Cpu size={14} />
                  VPN-узел
                  {resourceHistory && resourceHistory.sample_count > 0 && (
                    <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                      {resourceHistory.sample_count}
                    </Badge>
                  )}
                </TabsTrigger>
                {isAdmin && (
                  <TabsTrigger value="panel" className="gap-1.5">
                    <LayoutDashboard size={14} />
                    Панель
                  </TabsTrigger>
                )}
              </TabsList>

              <TabsContent value="connections" className="space-y-4">
                <Card>
                  <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Users size={18} />
                        VPN-клиенты
                      </CardTitle>
                      <CardDescription>
                        {totalConnections === 0
                          ? 'Нет активных подключений'
                          : `${filteredOpenVpn.length + filteredWireGuard.length} из ${openvpnClients.length + wireguardPeers.length} записей`}
                      </CardDescription>
                    </div>
                    <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
                      <div className="relative sm:w-56">
                        <Search
                          size={14}
                          className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                        />
                        <Input
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          placeholder="Поиск по имени, IP..."
                          className="h-9 pl-9 text-xs"
                        />
                      </div>
                      <Select
                        value={protocolFilter}
                        onValueChange={(v) => setProtocolFilter(v as ProtocolFilter)}
                      >
                        <SelectTrigger className="h-9 w-full text-xs sm:w-40">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">Все протоколы</SelectItem>
                          <SelectItem value="openvpn">OpenVPN</SelectItem>
                          <SelectItem value="wireguard">WireGuard</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {totalConnections === 0 ? (
                      <EmptyState
                        icon={WifiOff}
                        title="Нет подключённых клиентов"
                        description="Активные VPN-сессии OpenVPN и WireGuard появятся здесь после подключения пользователей"
                        className="py-8"
                      />
                    ) : !hasFilteredClients ? (
                      <EmptyState
                        icon={Search}
                        title="Нет совпадений"
                        description="Измените поисковый запрос или сбросьте фильтр протокола"
                        className="py-8"
                      />
                    ) : (
                      <div
                        className={cn(
                          'grid gap-4',
                          showOpenVpn && showWireGuard && 'lg:grid-cols-2',
                        )}
                      >
                        {showOpenVpn && (
                          <Card className="border-dashed shadow-none">
                            <CardHeader className="pb-3">
                              <CardTitle className="flex items-center gap-2 text-base">
                                <Wifi size={16} />
                                OpenVPN
                              </CardTitle>
                              <CardDescription>
                                {filteredOpenVpn.length} активных клиентов
                              </CardDescription>
                            </CardHeader>
                            <CardContent>
                              {filteredOpenVpn.length === 0 ? (
                                <EmptyState
                                  icon={WifiOff}
                                  title="Нет клиентов OpenVPN"
                                  description="Нет совпадений по текущему фильтру"
                                  className="py-6"
                                />
                              ) : (
                                <>
                                  <div className="space-y-3 lg:hidden">
                                    {filteredOpenVpn.map((c) => (
                                      <OpenVpnClientCard
                                        key={`${c.common_name}-${c.real_address}`}
                                        client={c}
                                      />
                                    ))}
                                  </div>
                                  <div className="hidden overflow-x-auto rounded-md border lg:block">
                                    <Table>
                                      <TableHeader>
                                        <TableRow>
                                          <TableHead>Статус</TableHead>
                                          <TableHead>Клиент</TableHead>
                                          <TableHead>Real IP</TableHead>
                                          <TableHead>VPN IP</TableHead>
                                          <TableHead className="text-right">RX</TableHead>
                                          <TableHead className="text-right">TX</TableHead>
                                          <TableHead>Подключён с</TableHead>
                                        </TableRow>
                                      </TableHeader>
                                      <TableBody>
                                        {filteredOpenVpn.map((c) => (
                                          <TableRow key={`${c.common_name}-${c.real_address}`}>
                                            <TableCell>
                                              <div className="flex flex-wrap items-center gap-1">
                                                <Badge variant="default" className="text-[10px]">
                                                  OVPN
                                                </Badge>
                                                <Badge variant="success" className="text-[10px]">
                                                  Онлайн
                                                </Badge>
                                              </div>
                                            </TableCell>
                                            <TableCell className="font-medium">{c.common_name}</TableCell>
                                            <TableCell className="font-mono text-xs">{c.real_address}</TableCell>
                                            <TableCell className="font-mono text-xs">{c.virtual_address}</TableCell>
                                            <TableCell className="text-right font-mono text-xs">
                                              <span className="inline-flex items-center justify-end gap-1">
                                                <ArrowDownToLine size={12} className="text-primary" />
                                                {formatBytes(c.bytes_received)}
                                              </span>
                                            </TableCell>
                                            <TableCell className="text-right font-mono text-xs">
                                              <span className="inline-flex items-center justify-end gap-1">
                                                <ArrowUpFromLine size={12} className="text-amber-500" />
                                                {formatBytes(c.bytes_sent)}
                                              </span>
                                            </TableCell>
                                            <TableCell className="text-xs text-muted-foreground">
                                              <span className="inline-flex items-center gap-1">
                                                <Clock size={12} className="shrink-0" />
                                                {c.connected_since}
                                              </span>
                                            </TableCell>
                                          </TableRow>
                                        ))}
                                      </TableBody>
                                    </Table>
                                  </div>
                                </>
                              )}
                            </CardContent>
                          </Card>
                        )}

                        {showWireGuard && (
                          <Card className="border-dashed shadow-none">
                            <CardHeader className="pb-3">
                              <CardTitle className="flex items-center gap-2 text-base">
                                <Radio size={16} />
                                WireGuard / AmneziaWG
                              </CardTitle>
                              <CardDescription>
                                {filteredWireGuard.filter(isWireGuardOnline).length} онлайн из{' '}
                                {filteredWireGuard.length} пиров
                              </CardDescription>
                            </CardHeader>
                            <CardContent>
                              {filteredWireGuard.length === 0 ? (
                                <EmptyState
                                  icon={WifiOff}
                                  title="Нет пиров WireGuard"
                                  description="Нет совпадений по текущему фильтру"
                                  className="py-6"
                                />
                              ) : (
                                <>
                                  <div className="space-y-3 lg:hidden">
                                    {filteredWireGuard.map((p) => (
                                      <WireGuardPeerCard
                                        key={`${p.interface}-${p.public_key}`}
                                        peer={p}
                                      />
                                    ))}
                                  </div>
                                  <div className="hidden overflow-x-auto rounded-md border lg:block">
                                    <Table>
                                      <TableHeader>
                                        <TableRow>
                                          <TableHead>Статус</TableHead>
                                          <TableHead>IF</TableHead>
                                          <TableHead>Клиент</TableHead>
                                          <TableHead>Endpoint</TableHead>
                                          <TableHead>IP</TableHead>
                                          <TableHead className="text-right">RX</TableHead>
                                          <TableHead className="text-right">TX</TableHead>
                                          <TableHead>Handshake</TableHead>
                                        </TableRow>
                                      </TableHeader>
                                      <TableBody>
                                        {filteredWireGuard.map((p) => {
                                          const online = isWireGuardOnline(p)
                                          return (
                                            <TableRow
                                              key={`${p.interface}-${p.public_key}`}
                                              className={cn(online && 'bg-emerald-500/5')}
                                            >
                                              <TableCell>
                                                <div className="flex flex-wrap items-center gap-1">
                                                  <Badge variant="secondary" className="text-[10px]">
                                                    WG
                                                  </Badge>
                                                  <Badge
                                                    variant={online ? 'success' : 'secondary'}
                                                    className="text-[10px]"
                                                  >
                                                    {online ? 'Онлайн' : 'Офлайн'}
                                                  </Badge>
                                                </div>
                                              </TableCell>
                                              <TableCell className="font-mono text-xs">{p.interface}</TableCell>
                                              <TableCell className="font-medium">
                                                {p.client_name || '—'}
                                              </TableCell>
                                              <TableCell className="font-mono text-xs">{p.endpoint || '—'}</TableCell>
                                              <TableCell className="font-mono text-xs">{p.allowed_ips || '—'}</TableCell>
                                              <TableCell className="text-right font-mono text-xs">
                                                {formatBytes(p.transfer_rx)}
                                              </TableCell>
                                              <TableCell className="text-right font-mono text-xs">
                                                {formatBytes(p.transfer_tx)}
                                              </TableCell>
                                              <TableCell className="text-xs text-muted-foreground">
                                                {formatHandshake(p.latest_handshake)}
                                              </TableCell>
                                            </TableRow>
                                          )
                                        })}
                                      </TableBody>
                                    </Table>
                                  </div>
                                </>
                              )}
                            </CardContent>
                          </Card>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="services" className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Server size={18} />
                      Матрица служб
                    </CardTitle>
                    <CardDescription>
                      {activeServices} из {totalServices} служб online
                      {data?.server_ip && <> · IP {data.server_ip}</>}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {totalServices === 0 ? (
                      <EmptyState
                        icon={Server}
                        title="Нет данных о службах"
                        description="Список служб появится после успешного опроса узла"
                        className="py-8"
                      />
                    ) : (
                      <ServiceMatrix services={data.services} />
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              {isAdmin && (
                <TabsContent value="panel" className="space-y-4">
                  <PanelResourceHistoryCharts
                    period={panelResourcePeriod}
                    onPeriodChange={setPanelResourcePeriod}
                  />
                </TabsContent>
              )}

              <TabsContent value="resources" className="space-y-4">
                <SettingsAlert variant="info" title="Ресурсы VPN-узла, не панели">
                  История CPU/RAM/диска относится к серверу AntiZapret (VPN, маршрутизация, службы), с которого
                  собираются данные. Снимки пишет панель с активного узла{' '}
                  <strong>{activeNode?.name ?? data?.node_name ?? '—'}</strong> каждые ~60 с. Для live-метрик
                  откройте «Мониторинг сервера».
                </SettingsAlert>
                <ResourceHistoryCharts
                  data={resourceHistory}
                  loading={resourceLoading}
                  period={resourcePeriod}
                  onPeriodChange={setResourcePeriod}
                />
              </TabsContent>
            </Tabs>
          </>
        )
      )}
    </div>
  )
}
