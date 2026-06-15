import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
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
import { ApiError, getMonitoring, getResourceHistory, openMonitoringStream } from '@/api/client'
import MonitoringCharts, { formatBytes, totalTraffic } from '@/components/monitoring/MonitoringCharts'
import MonitoringConnectionsList, {
  buildMonitoringConnectionRows,
} from '@/components/monitoring/MonitoringConnectionsList'
import MonitoringGeoSummary from '@/components/monitoring/MonitoringGeoSummary'
import { NodeScopeBadge, getConnectionDisplayAddress, getConnectionGeoLabel } from '@/components/monitoring/ConnectionAddress'
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
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
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
import type { MonitoringNodeSummary, MonitoringOverview, ResourceHistory, WireGuardPeer } from '@/types'

const REFRESH_INTERVAL = 30

type MonitoringScope = 'node' | 'all'
type ProtocolFilter = 'all' | 'openvpn' | 'wireguard'

function dataSourceLabel(source?: string) {
  if (source === 'federated') return 'Все узлы'
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

export default function MonitoringPage() {
  const { user } = useAuth()
  const { activeNode, nodes } = useNode()
  const isAdmin = user?.role === 'admin'
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal } = useProgress()
  const [scope, setScope] = useState<MonitoringScope>('node')
  const [data, setData] = useState<MonitoringOverview | null>(null)
  const [liveLoading, setLiveLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const [search, setSearch] = useState('')
  const [onlineOnly, setOnlineOnly] = useState(true)
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
        setLiveLoading(true)
        startGlobal()
      } else if (manual) {
        setRefreshing(true)
      }
      try {
        setData(await getMonitoring(scope))
        setLoadError(null)
        if (manual) success('Данные мониторинга обновлены')
        setCountdown(REFRESH_INTERVAL)
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Ошибка загрузки мониторинга'
        setLoadError(message)
        notifyError(message)
      } finally {
        setLiveLoading(false)
        setRefreshing(false)
        if (initial) doneGlobal()
      }
    },
    [startGlobal, doneGlobal, success, notifyError, scope],
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
  }, [load, activeNode?.id, scope])

  useEffect(() => {
    loadResourceHistory(resourcePeriod)
  }, [loadResourceHistory, activeNode?.id, resourcePeriod])

  useEffect(() => {
    if (!autoRefresh || scope !== 'node') return

    const source = openMonitoringStream(
      (payload) => {
        setData(payload)
        setLoadError(null)
        setCountdown(REFRESH_INTERVAL)
      },
      () => {},
    )

    const tick = setInterval(() => {
      setCountdown((c) => (c <= 1 ? REFRESH_INTERVAL : c - 1))
    }, 1000)

    return () => {
      source?.close()
      clearInterval(tick)
    }
  }, [autoRefresh, scope, activeNode?.id])

  useEffect(() => {
    if (!autoRefresh || scope !== 'all') return
    const poll = setInterval(() => {
      void loadRef.current?.()
    }, REFRESH_INTERVAL * 1000)
    const tick = setInterval(() => {
      setCountdown((c) => (c <= 1 ? REFRESH_INTERVAL : c - 1))
    }, 1000)
    return () => {
      clearInterval(poll)
      clearInterval(tick)
    }
  }, [autoRefresh, scope])

  const isFederated = scope === 'all' || data?.scope === 'all'
  const showNodeColumn = isFederated
  const hasMultipleNodes = nodes.length > 1

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
    return openvpnClients.filter((c) => {
      const address = getConnectionDisplayAddress(c).toLowerCase()
      const geo = (getConnectionGeoLabel(c) || '').toLowerCase()
      return (
        c.common_name.toLowerCase().includes(searchQuery) ||
        address.includes(searchQuery) ||
        geo.includes(searchQuery) ||
        c.virtual_address.toLowerCase().includes(searchQuery) ||
        (c.node_name || '').toLowerCase().includes(searchQuery)
      )
    })
  }, [openvpnClients, searchQuery])

  const filteredWireGuard = useMemo(() => {
    if (!searchQuery) return wireguardPeers
    return wireguardPeers.filter((p) => {
      const name = (p.client_name ?? '').toLowerCase()
      const address = getConnectionDisplayAddress(p, 'endpoint').toLowerCase()
      const geo = (getConnectionGeoLabel(p) || '').toLowerCase()
      return (
        name.includes(searchQuery) ||
        address.includes(searchQuery) ||
        geo.includes(searchQuery) ||
        (p.endpoint ?? '').toLowerCase().includes(searchQuery) ||
        (p.allowed_ips ?? '').toLowerCase().includes(searchQuery) ||
        p.interface.toLowerCase().includes(searchQuery) ||
        p.public_key.toLowerCase().includes(searchQuery) ||
        (p.node_name || '').toLowerCase().includes(searchQuery)
      )
    })
  }, [wireguardPeers, searchQuery])

  const visibleWireGuard = useMemo(() => {
    if (!onlineOnly) return filteredWireGuard
    return filteredWireGuard.filter(isWireGuardOnline)
  }, [filteredWireGuard, onlineOnly])

  const showOpenVpn = protocolFilter === 'all' || protocolFilter === 'openvpn'
  const showWireGuard = protocolFilter === 'all' || protocolFilter === 'wireguard'
  const visibleOpenVpn = showOpenVpn ? filteredOpenVpn : []
  const visibleWireGuardList = showWireGuard ? visibleWireGuard : []
  const visibleCount = visibleOpenVpn.length + visibleWireGuardList.length
  const filteredTotalCount =
    (showOpenVpn ? filteredOpenVpn.length : 0) + (showWireGuard ? filteredWireGuard.length : 0)
  const hasFilteredClients = visibleCount > 0

  const connectionRows = useMemo(
    () =>
      buildMonitoringConnectionRows(visibleOpenVpn, visibleWireGuardList, {
        showOpenVpn,
        showWireGuard,
        isWireGuardOnline,
      }),
    [visibleOpenVpn, visibleWireGuardList, showOpenVpn, showWireGuard],
  )

  const handleRefresh = () => {
    load({ manual: true })
    loadResourceHistory(resourcePeriod)
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
              <NodeBadge
                name={isFederated ? `Все узлы (${data?.nodes_online ?? 0}/${data?.nodes_total ?? nodes.length})` : (activeNode?.name ?? data?.node_name)}
                status={isFederated ? 'online' : activeNode?.status}
              />
            </div>
            <p className="text-sm text-muted-foreground">
              {isFederated
                ? 'Сводка активных VPN-подключений со всех узлов'
                : 'Активные VPN-подключения OpenVPN и WireGuard в реальном времени'}
              {data?.timestamp && (
                <> · обновлено {new Date(data.timestamp).toLocaleString('ru-RU')}</>
              )}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {hasMultipleNodes && (
            <Select value={scope} onValueChange={(v) => setScope(v as MonitoringScope)}>
              <SelectTrigger className="h-9 w-[180px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="node">Активный узел</SelectItem>
                <SelectItem value="all">Все узлы</SelectItem>
              </SelectContent>
            </Select>
          )}
          <AutoRefreshControl
          enabled={autoRefresh}
          onToggle={() => setAutoRefresh((v) => !v)}
          countdown={countdown}
          intervalSec={REFRESH_INTERVAL}
          refreshing={refreshing}
          onManualRefresh={handleRefresh}
          />
        </div>
      </div>

      <SettingsAlert variant="info" title={isFederated ? 'Сводка по всем узлам' : 'Данные активного узла'}>
        {isFederated ? (
          <>
            Показаны подключения с <strong>{data?.nodes_total ?? nodes.length}</strong> узлов · online{' '}
            <strong>{data?.nodes_online ?? 0}</strong>. Геолокация IP — приблизительный город и провайдер.
          </>
        ) : (
          <>
            Мониторинг собирается с <strong>{activeNode?.name ?? data?.node_name ?? 'активного узла'}</strong>
            {activeNode?.is_local ? ' (локальный controller)' : ' (удалённый node agent)'}.
            Автообновление каждые {REFRESH_INTERVAL} с. Переключите узел в шапке или на странице «Узлы».
          </>
        )}
      </SettingsAlert>

      {!isFederated && nodeOffline && (
        <SettingsAlert variant="warning" title="Узел офлайн">
          Активный узел недоступен. Данные подключений могут быть устаревшими или отсутствовать.
          Проверьте связь с node agent и повторите обновление.
        </SettingsAlert>
      )}

      {!isFederated && nodeUnknown && !nodeOffline && (
        <SettingsAlert variant="warning" title="Статус узла неизвестен">
          Связь с узлом не подтверждена. Запустите проверку здоровья на странице «Узлы».
        </SettingsAlert>
      )}

      <InlineProgressBar active={refreshing} label="Обновление данных мониторинга..." />

      {liveLoading && !data && !loadError ? (
        <Card>
          <CardContent>
            <Spinner label="Загрузка live-данных с узла..." className="py-12" />
          </CardContent>
        </Card>
      ) : loadError && !data ? (
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
                {isFederated
                  ? `Узлы: ${data.nodes_online ?? 0}/${data.nodes_total ?? 0}`
                  : `Службы: ${activeServices}/${totalServices}`}
              </Badge>
            </div>

            {isFederated && (data.nodes_summary?.length ?? 0) > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Server size={18} />
                    Сводка по узлам
                  </CardTitle>
                  <CardDescription>
                    Подключения и службы на каждом VPN-узле
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Узел</TableHead>
                          <TableHead>Статус</TableHead>
                          <TableHead className="text-right">OpenVPN</TableHead>
                          <TableHead className="text-right">WireGuard</TableHead>
                          <TableHead className="text-right">Службы</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.nodes_summary?.map((node: MonitoringNodeSummary) => (
                          <TableRow key={node.node_id}>
                            <TableCell className="font-medium">{node.node_name}</TableCell>
                            <TableCell>
                              <Badge variant={node.status === 'online' ? 'success' : 'secondary'} className="text-[10px]">
                                {node.status === 'online' ? 'Online' : node.status}
                              </Badge>
                              {node.error && (
                                <p className="mt-1 text-[11px] text-destructive">{node.error}</p>
                              )}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs">{node.connected_openvpn}</TableCell>
                            <TableCell className="text-right font-mono text-xs">{node.connected_wireguard}</TableCell>
                            <TableCell className="text-right font-mono text-xs">
                              {node.active_services}/{node.total_services}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            )}

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <SummaryCard
                label="OpenVPN онлайн"
                value={String(isFederated ? data.total_connected_openvpn ?? openvpnClients.length : openvpnClients.length)}
                icon={Wifi}
                accent="text-primary"
                sub="активных сессий"
              />
              <SummaryCard
                label="WireGuard онлайн"
                value={String(isFederated ? data.total_connected_wireguard ?? wgActive : wgActive)}
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

            <div className="space-y-4">
              <MonitoringCharts data={data} />
              {totalConnections > 0 && hasFilteredClients && (
                <MonitoringGeoSummary
                  openvpnClients={visibleOpenVpn}
                  wireguardPeers={visibleWireGuardList}
                  showOpenVpn={showOpenVpn}
                  showWireGuard={showWireGuard}
                  isWireGuardOnline={isWireGuardOnline}
                  onlineOnly={onlineOnly}
                />
              )}
            </div>

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
                  <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="shrink-0">
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Users size={18} />
                        VPN-клиенты
                      </CardTitle>
                      <CardDescription>
                        {totalConnections === 0
                          ? 'Нет активных подключений'
                          : onlineOnly
                            ? `${visibleCount} онлайн${filteredTotalCount > visibleCount ? ` из ${filteredTotalCount}` : ''}`
                            : `${visibleCount} из ${openvpnClients.length + wireguardPeers.length} записей`}
                      </CardDescription>
                    </div>
                    <div className="flex w-full flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center lg:w-auto lg:justify-end">
                      <div className="relative w-full sm:w-56">
                        <Search
                          size={14}
                          className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                        />
                        <Input
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          placeholder="Поиск по имени, IP, городу..."
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
                      <div className="flex h-9 shrink-0 items-center gap-2">
                        <Switch
                          id="monitoring-online-only"
                          checked={onlineOnly}
                          onCheckedChange={setOnlineOnly}
                        />
                        <Label htmlFor="monitoring-online-only" className="whitespace-nowrap text-xs text-muted-foreground">
                          Только онлайн
                        </Label>
                      </div>
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
                        description={
                          onlineOnly && filteredTotalCount > 0
                            ? 'Снимите фильтр «Только онлайн» или измените поисковый запрос'
                            : 'Измените поисковый запрос или сбросьте фильтр протокола'
                        }
                        className="py-8"
                      />
                    ) : (
                      <MonitoringConnectionsList rows={connectionRows} showNodeColumn={showNodeColumn} />
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="services" className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Server size={18} />
                      {isFederated ? 'Службы по узлам' : 'Матрица служб'}
                    </CardTitle>
                    <CardDescription>
                      {isFederated
                        ? 'Для детальной матрицы переключитесь на режим «Активный узел»'
                        : `${activeServices} из ${totalServices} служб online`}
                      {!isFederated && data?.server_ip && <> · IP {data.server_ip}</>}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {isFederated ? (
                      (data.nodes_summary?.length ?? 0) === 0 ? (
                        <EmptyState
                          icon={Server}
                          title="Нет данных по узлам"
                          description="Список узлов появится после успешного опроса"
                          className="py-8"
                        />
                      ) : (
                        <div className="overflow-x-auto rounded-md border">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>Узел</TableHead>
                                <TableHead>Статус</TableHead>
                                <TableHead className="text-right">Online</TableHead>
                                <TableHead className="text-right">Всего</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {data.nodes_summary?.map((node) => (
                                <TableRow key={node.node_id}>
                                  <TableCell>{node.node_name}</TableCell>
                                  <TableCell>{node.status}</TableCell>
                                  <TableCell className="text-right font-mono text-xs">{node.active_services}</TableCell>
                                  <TableCell className="text-right font-mono text-xs">{node.total_services}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      )
                    ) : totalServices === 0 ? (
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
