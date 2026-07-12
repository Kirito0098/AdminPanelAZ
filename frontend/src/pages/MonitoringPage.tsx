import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  ChevronRight,
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
import GeoRoutingHintBanner from '@/components/dashboard/GeoRoutingHintBanner'
import NodesCompareSection from '@/components/dashboard/NodesCompareSection'
import MonitoringCharts, { formatBytes, totalTraffic } from '@/components/monitoring/MonitoringCharts'
import MonitoringConnectionsList, {
  buildMonitoringConnectionRows,
} from '@/components/monitoring/MonitoringConnectionsList'
import MonitoringGeoSummary from '@/components/monitoring/MonitoringGeoSummary'
import NodeSummaryCard from '@/components/monitoring/NodeSummaryCard'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import { getConnectionDisplayAddress, getConnectionGeoLabel } from '@/components/monitoring/ConnectionAddress'
import PanelResourceHistoryCharts from '@/components/monitoring/PanelResourceHistoryCharts'
import ResourceHistoryCharts from '@/components/monitoring/ResourceHistoryCharts'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import ServiceMatrix from '@/components/noc/ServiceMatrix'
import { NodeBadge, NodeStatusBadge } from '@/components/NodeSelector'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
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
import { formatDateTime } from '@/lib/datetime'
import { isResourceCritical, metricBarClass } from '@/lib/metricColors'
import { connectionSourceLabel } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import { isWireGuardOnline } from '@/lib/wireguardStatus'
import type { MonitoringNodeSummary, MonitoringOverview, NodeStatus, ResourceHistory } from '@/types'

const REFRESH_INTERVAL = 30
const STORAGE_PREFIX = 'noc-monitoring'

type MonitoringScope = 'node' | 'all'
type ProtocolFilter = 'all' | 'openvpn' | 'wireguard'

function readStored<T extends string>(key: string, allowed: readonly T[]): T | null {
  if (typeof window === 'undefined') return null
  try {
    const value = window.localStorage.getItem(`${STORAGE_PREFIX}:${key}`)
    return value && (allowed as readonly string[]).includes(value) ? (value as T) : null
  } catch {
    return null
  }
}

function writeStored(key: string, value: string) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}:${key}`, value)
  } catch {
    /* ignore quota / privacy mode */
  }
}

function dataSourceLabel(source?: string) {
  if (source === 'federated') return 'Все узлы'
  if (source === 'management_socket') return connectionSourceLabel('management_socket')
  if (source === 'status_log') return 'Status-логи'
  return 'Нет данных'
}

function dataSourceVariant(source?: string): 'default' | 'secondary' | 'outline' {
  if (source === 'management_socket') return 'default'
  if (source === 'status_log') return 'secondary'
  return 'outline'
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
    <Card className="transition-colors hover:border-primary/30">
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

function formatMetricPercent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

function MetricProgress({ value }: { value: number }) {
  const clamped = Math.min(100, Math.max(0, value))
  return <Progress value={clamped} barClassName={metricBarClass(value)} className="h-2" />
}

type ScopeToggleProps = {
  value: MonitoringScope
  onChange: (scope: MonitoringScope) => void
  nodesOnline?: number
  nodesTotal?: number
}

function ScopeToggle({ value, onChange, nodesOnline, nodesTotal }: ScopeToggleProps) {
  const options: { id: MonitoringScope; label: string; icon: typeof Server }[] = [
    { id: 'node', label: 'Активный узел', icon: Server },
    { id: 'all', label: 'Все узлы', icon: Globe },
  ]
  return (
    <div className="inline-flex h-9 items-center rounded-lg border bg-muted/40 p-0.5">
      {options.map((opt) => {
        const active = value === opt.id
        const Icon = opt.icon
        return (
          <button
            key={opt.id}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(opt.id)}
            className={cn(
              'inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors',
              active
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon size={14} />
            {opt.label}
            {opt.id === 'all' && active && nodesTotal != null && (
              <span className="ml-0.5 rounded bg-primary/10 px-1 text-[10px] font-semibold tabular-nums text-primary">
                {nodesOnline ?? 0}/{nodesTotal}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

export default function MonitoringPage() {
  const { user } = useAuth()
  const { activeNode, nodes, loading: nodesLoading, activate } = useNode()
  const isAdmin = user?.role === 'admin'
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal } = useProgress()
  const [scope, setScope] = useState<MonitoringScope>(() => readStored('scope', ['node', 'all'] as const) ?? 'node')
  const [scopeInitialized, setScopeInitialized] = useState(() => readStored('scope', ['node', 'all'] as const) != null)
  const [data, setData] = useState<MonitoringOverview | null>(null)
  const [liveLoading, setLiveLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const [search, setSearch] = useState('')
  const [onlineOnly, setOnlineOnly] = useState(() => readStored('onlineOnly', ['true', 'false'] as const) !== 'false')
  const [protocolFilter, setProtocolFilter] = useState<ProtocolFilter>(
    () => readStored('protocol', ['all', 'openvpn', 'wireguard'] as const) ?? 'all',
  )
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

  useEffect(() => {
    if (nodesLoading || scopeInitialized) return
    if (nodes.length > 1) setScope('all')
    setScopeInitialized(true)
  }, [nodesLoading, nodes.length, scopeInitialized])

  useEffect(() => {
    if (scopeInitialized) writeStored('scope', scope)
  }, [scope, scopeInitialized])

  useEffect(() => {
    writeStored('onlineOnly', String(onlineOnly))
  }, [onlineOnly])

  useEffect(() => {
    writeStored('protocol', protocolFilter)
  }, [protocolFilter])

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
    if (nodesLoading && !scopeInitialized) return
    load({ initial: true })
  }, [load, activeNode?.id, scope, nodesLoading, scopeInitialized])

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
        (c.node_name || '').toLowerCase().includes(searchQuery) ||
        (c.ha?.shared_domain || '').toLowerCase().includes(searchQuery)
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
        (p.node_name || '').toLowerCase().includes(searchQuery) ||
        (p.ha?.shared_domain || '').toLowerCase().includes(searchQuery)
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

  const goToNode = useCallback(
    (nodeId: number, nodeName: string) => {
      const target = nodes.find((n) => n.id === nodeId)
      if (target && target.id !== activeNode?.id) {
        void activate(nodeId)
          .then(() => success(`Активный узел: ${nodeName}`))
          .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка активации узла'))
      }
      setScope('node')
    },
    [nodes, activeNode?.id, activate, success, notifyError],
  )

  const sortedNodeSummary = useMemo(() => {
    const list = data?.nodes_summary ?? []
    const rank = (status: string) => (status === 'online' ? 2 : status === 'offline' ? 0 : 1)
    return [...list].sort((a, b) => {
      const byStatus = rank(a.status) - rank(b.status)
      if (byStatus !== 0) return byStatus
      return a.node_name.localeCompare(b.node_name)
    })
  }, [data?.nodes_summary])

  const nodeHealthIssues = useMemo(() => {
    if (!isFederated) return { offline: [], overloaded: [] as string[] }
    const list = data?.nodes_summary ?? []
    const offline = list.filter((n) => n.status !== 'online').map((n) => n.node_name)
    const overloaded = list
      .filter(
        (n) =>
          n.status === 'online' &&
          (isResourceCritical(n.cpu_percent) || isResourceCritical(n.memory_percent)),
      )
      .map((n) => {
        const parts: string[] = []
        if (isResourceCritical(n.cpu_percent)) parts.push(`CPU ${formatMetricPercent(n.cpu_percent)}`)
        if (isResourceCritical(n.memory_percent)) parts.push(`RAM ${formatMetricPercent(n.memory_percent)}`)
        return `${n.node_name} (${parts.join(', ')})`
      })
    return { offline, overloaded }
  }, [isFederated, data?.nodes_summary])

  const hasHealthIssues = nodeHealthIssues.offline.length > 0 || nodeHealthIssues.overloaded.length > 0

  return (
    <div className="space-y-6">
      <PageSectionHeader
        icon={Radio}
        title="NOC Мониторинг"
        titleAddon={
          <NodeBadge
            name={
              isFederated
                ? `Все узлы (${data?.nodes_online ?? 0}/${data?.nodes_total ?? nodes.length})`
                : (activeNode?.name ?? data?.node_name)
            }
            status={isFederated ? 'online' : activeNode?.status}
          />
        }
        description={
          <>
            {isFederated
              ? 'Сводка активных VPN-подключений со всех узлов'
              : 'Активные VPN-подключения OpenVPN и WireGuard в реальном времени'}
            {data?.timestamp && <> · обновлено {formatDateTime(data.timestamp)}</>}
          </>
        }
        actions={
          <>
            {hasMultipleNodes && (
              <ScopeToggle
                value={scope}
                onChange={setScope}
                nodesOnline={data?.nodes_online}
                nodesTotal={data?.nodes_total ?? nodes.length}
              />
            )}
            <AutoRefreshControl
              enabled={autoRefresh}
              onToggle={() => setAutoRefresh((v) => !v)}
              countdown={countdown}
              intervalSec={REFRESH_INTERVAL}
              refreshing={refreshing}
              onManualRefresh={handleRefresh}
            />
          </>
        }
      />

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

      <GeoRoutingHintBanner enabled={hasMultipleNodes} />

      {isFederated && hasHealthIssues && (
        <SettingsAlert
          variant={nodeHealthIssues.offline.length > 0 ? 'danger' : 'warning'}
          title="Требуют внимания"
        >
          <div className="space-y-1">
            {nodeHealthIssues.offline.length > 0 && (
              <p>
                Недоступны ({nodeHealthIssues.offline.length}):{' '}
                <strong>{nodeHealthIssues.offline.join(', ')}</strong>
              </p>
            )}
            {nodeHealthIssues.overloaded.length > 0 && (
              <p>
                Высокая нагрузка: <strong>{nodeHealthIssues.overloaded.join(' · ')}</strong>
              </p>
            )}
          </div>
        </SettingsAlert>
      )}

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
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <Skeleton className="h-3 w-24" />
                    <Skeleton className="h-8 w-8 rounded-md" />
                  </div>
                  <Skeleton className="mt-3 h-7 w-16" />
                  <Skeleton className="mt-2 h-3 w-28" />
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardContent className="p-4">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="mt-4 h-48 w-full" />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-3 p-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </CardContent>
          </Card>
        </div>
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
                    Подключения и службы на каждом VPN-узле · нажмите на узел, чтобы открыть его детально
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ResponsiveDataView
                    mobile={sortedNodeSummary.map((node: MonitoringNodeSummary) => (
                      <NodeSummaryCard
                        key={node.node_id}
                        node={node}
                        isActive={node.node_id === activeNode?.id}
                        onSelect={() => goToNode(node.node_id, node.node_name)}
                      />
                    ))}
                    desktop={
                      <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Узел</TableHead>
                          <TableHead>Статус</TableHead>
                          <TableHead className="text-right">OpenVPN</TableHead>
                          <TableHead className="text-right">WireGuard</TableHead>
                          <TableHead className="text-right">Службы</TableHead>
                          <TableHead>CPU</TableHead>
                          <TableHead>RAM</TableHead>
                          <TableHead className="text-right">Трафик</TableHead>
                          <TableHead className="text-right">CIDR</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sortedNodeSummary.map((node: MonitoringNodeSummary) => {
                          const isActive = node.node_id === activeNode?.id
                          return (
                            <TableRow
                              key={node.node_id}
                              onClick={() => goToNode(node.node_id, node.node_name)}
                              className={cn(
                                'group cursor-pointer transition-colors',
                                node.status === 'offline' && 'bg-destructive/5 hover:bg-destructive/10',
                                isActive && 'bg-primary/5',
                              )}
                            >
                              <TableCell className="font-medium">
                                <span className="inline-flex items-center gap-1.5">
                                  <ChevronRight
                                    size={14}
                                    className="text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
                                  />
                                  {node.node_name}
                                  {isActive && (
                                    <Badge variant="outline" className="h-4 px-1 text-[10px]">
                                      активный
                                    </Badge>
                                  )}
                                </span>
                              </TableCell>
                              <TableCell>
                                <NodeStatusBadge status={node.status as NodeStatus} />
                                {node.error && (
                                  <p className="mt-1 text-[11px] text-destructive">{node.error}</p>
                                )}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">{node.connected_openvpn}</TableCell>
                              <TableCell className="text-right font-mono text-xs">{node.connected_wireguard}</TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {node.active_services}/{node.total_services}
                              </TableCell>
                              <TableCell className="min-w-[110px]">
                                {node.cpu_percent != null ? (
                                  <div className="space-y-1">
                                    <MetricProgress value={node.cpu_percent} />
                                    <span className="text-[10px] text-muted-foreground">
                                      {formatMetricPercent(node.cpu_percent)}
                                    </span>
                                  </div>
                                ) : (
                                  <span className="text-xs text-muted-foreground">н/д</span>
                                )}
                              </TableCell>
                              <TableCell className="min-w-[110px]">
                                {node.memory_percent != null ? (
                                  <div className="space-y-1">
                                    <MetricProgress value={node.memory_percent} />
                                    <span className="text-[10px] text-muted-foreground">
                                      {formatMetricPercent(node.memory_percent)}
                                    </span>
                                  </div>
                                ) : (
                                  <span className="text-xs text-muted-foreground">н/д</span>
                                )}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {node.total_traffic_bytes != null ? formatBytes(node.total_traffic_bytes) : '—'}
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs">
                                {node.cidr_routes_count ?? '—'}
                              </TableCell>
                            </TableRow>
                          )
                        })}
                      </TableBody>
                    </Table>
                    }
                    mobileClassName="space-y-3"
                    desktopClassName="overflow-x-auto rounded-md border"
                  />
                </CardContent>
              </Card>
            )}

            {isFederated && hasMultipleNodes && <NodesCompareSection collapsible defaultOpen={false} />}

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
                        <Label htmlFor="monitoring-online-only" className="text-xs text-muted-foreground">
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
                              {sortedNodeSummary.map((node) => (
                                <TableRow
                                  key={node.node_id}
                                  onClick={() => goToNode(node.node_id, node.node_name)}
                                  className={cn(
                                    'group cursor-pointer transition-colors',
                                    node.status === 'offline' && 'bg-destructive/5 hover:bg-destructive/10',
                                  )}
                                >
                                  <TableCell className="font-medium">
                                    <span className="inline-flex items-center gap-1.5">
                                      <ChevronRight
                                        size={14}
                                        className="text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
                                      />
                                      {node.node_name}
                                    </span>
                                  </TableCell>
                                  <TableCell>
                                    <NodeStatusBadge status={node.status as NodeStatus} />
                                  </TableCell>
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
