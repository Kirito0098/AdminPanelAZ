import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import {
  Activity,
  ChevronRight,
  Cpu,
  Globe,
  Hash,
  LayoutDashboard,
  Loader2,
  Network,
  Radio,
  ScrollText,
  Search,
  Server,
  Users,
  Wifi,
  WifiOff,
} from 'lucide-react'
import {
  ApiError,
  getConnectionHistory,
  getMonitoring,
  getNocIncidents,
  getResourceHistory,
  openMonitoringStream,
  openvpnDisconnect,
  openvpnDisconnectSession,
  restartService,
  type StreamHandle,
} from '@/api/client'
import GeoRoutingHintBanner from '@/components/dashboard/GeoRoutingHintBanner'
import { formatBytes, totalTraffic } from '@/lib/trafficFormat'
import MonitoringConnectionsList, {
  buildMonitoringConnectionRows,
  type DeviceDisconnectTarget,
} from '@/components/monitoring/MonitoringConnectionsList'
import MonitoringUsersList from '@/components/monitoring/MonitoringUsersList'
import NodeSummaryCard from '@/components/monitoring/NodeSummaryCard'
import {
  HealthScoreBadge,
  ResourceMetricInline,
} from '@/components/monitoring/nodeSummaryMetrics'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import ViewModeToggle from '@/components/shared/ViewModeToggle'
import { DOCS } from '@/lib/docsUrls'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import { getConnectionDisplayAddress, getConnectionGeoLabel } from '@/components/monitoring/ConnectionAddress'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import NocConnectionFilters, {
  minDurationSeconds,
  NOC_FILTER_NONE,
  type MinDurationFilter,
  type NocSortKey,
} from '@/components/noc/NocConnectionFilters'
import NocDataFreshness from '@/components/noc/NocDataFreshness'
import NocIncidentFeed from '@/components/noc/NocIncidentFeed'
import ServiceMatrix from '@/components/noc/ServiceMatrix'
import { NodeBadge, NodeStatusBadge } from '@/components/NodeSelector'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
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
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useConnectionRates } from '@/hooks/useConnectionRates'
import { usePageTab } from '@/hooks/usePageTab'
import { isDocumentHidden } from '@/hooks/useIntervalWhenVisible'
import { formatDateTime } from '@/lib/datetime'
import { groupConnectionsByOwner } from '@/lib/connectionUserGroups'
import { cn } from '@/lib/utils'
import { isWireGuardOnline } from '@/lib/wireguardStatus'
import { createStorage } from '@/lib/safeStorage'
import type {
  ConnectionHistoryResponse,
  MonitoringNodeSummary,
  MonitoringOverview,
  NodeStatus,
  NocIncidentItem,
  ResourceHistory,
} from '@/types'

// Тяжёлые вкладки и графики грузим отдельными чанками: иначе их код и recharts
// попадают в чанк MonitoringPage и оттуда в общие чанки соседних страниц
// (см. scripts/check-entry-chunks.mjs).
const TrafficPage = lazy(() => import('@/pages/TrafficPage'))
const LogsPage = lazy(() => import('@/pages/LogsPage'))
const ServerMonitorPage = lazy(() => import('@/pages/ServerMonitorPage'))
const MonitoringCharts = lazy(() => import('@/components/monitoring/MonitoringCharts'))
const MonitoringGeoSummary = lazy(() => import('@/components/monitoring/MonitoringGeoSummary'))
const ResourceHistoryCharts = lazy(() => import('@/components/monitoring/ResourceHistoryCharts'))
const PanelResourceHistoryCharts = lazy(() => import('@/components/monitoring/PanelResourceHistoryCharts'))

const REFRESH_INTERVAL = 10
/** Incidents rebuild probes nodes; refresh far less often than SSE overview. */
const INCIDENTS_REFRESH_INTERVAL_MS = 60_000
const STORAGE_PREFIX = 'noc-monitoring'
const storage = createStorage(STORAGE_PREFIX)

type MonitoringScope = 'node' | 'all'
type ProtocolFilter = 'all' | 'openvpn' | 'wireguard' | 'amneziawg2'
type ConnectionsViewMode = 'configs' | 'users'
const PROTOCOL_FILTER_VALUES = ['all', 'openvpn', 'wireguard', 'amneziawg2'] as const

/** Вкладки «Наблюдения» (второй уровень после сайдбара). */
type MonitoringTab = 'connections' | 'services' | 'traffic' | 'resources' | 'logs'
/** Чипы-сегменты вкладки «Ресурсы»: что именно показываем. */
type ResourceScopeTab = 'node' | 'panel' | 'host'

const TAB_META: Record<MonitoringTab, { label: string; icon: typeof Server; docsHref: string; description: string }> = {
  connections: {
    label: 'Подключения',
    icon: Wifi,
    docsHref: DOCS.noc,
    description: 'Активные VPN-подключения OpenVPN и WireGuard в реальном времени',
  },
  services: {
    label: 'Службы',
    icon: Server,
    docsHref: DOCS.noc,
    description: 'Матрица служб узла и их состояние',
  },
  traffic: {
    label: 'Трафик',
    icon: Network,
    docsHref: DOCS.traffic,
    description: 'Накопленная статистика RX/TX по клиентам VPN и AntiZapret',
  },
  resources: {
    label: 'Ресурсы',
    icon: Cpu,
    docsHref: DOCS.serverMonitor,
    description: 'История CPU, RAM и диска узла, панели и хоста',
  },
  logs: {
    label: 'Журналы',
    icon: ScrollText,
    docsHref: DOCS.logs,
    description: 'События OpenVPN, действия администраторов, сокеты и уведомления',
  },
}

type SegmentOption<T extends string> = {
  id: T
  label: string
  icon?: typeof Server
  /** Дополнительный бейдж, виден только у активного сегмента. */
  hint?: ReactNode
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

type ChipSegmentsProps<T extends string> = {
  value: T
  onChange: (value: T) => void
  options: SegmentOption<T>[]
  ariaLabel: string
}

/** Заглушка до подгрузки чанка с recharts: без неё графики тянут панель на первом кадре. */
function ChartFallback() {
  return (
    <Card>
      <CardContent className="p-4">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="mt-4 h-56 w-full" />
      </CardContent>
    </Card>
  )
}

/** Чипы-сегменты третьего уровня: охват NOC и область «Ресурсов». */
function ChipSegments<T extends string>({ value, onChange, options, ariaLabel }: ChipSegmentsProps<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex h-9 items-center rounded-lg border bg-muted/40 p-0.5"
    >
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
            {Icon && <Icon size={14} />}
            {opt.label}
            {active && opt.hint}
          </button>
        )
      })}
    </div>
  )
}

export default function MonitoringPage() {
  const { user } = useAuth()
  const { activeNode, nodes, loading: nodeLoading, nodesLoading, activate } = useNode()
  const { isEnabled } = useFeatureModules()
  const awg2Enabled = isEnabled('awg2')
  const logsDashboardEnabled = isEnabled('logs_dashboard')
  const trafficSyncEnabled = isEnabled('traffic_sync')
  const serverMonitorEnabled = isEnabled('server_monitor')
  const actionLogsEnabled = isEnabled('action_logs')
  const isAdmin = user?.role === 'admin'

  // Вкладки фильтруются по флагам: пустых не показываем. Роль user в панели
  // видит только «Трафик» (раньше у неё был отдельный маршрут /traffic).
  const availableTabs = useMemo<MonitoringTab[]>(() => {
    if (!isAdmin) return trafficSyncEnabled ? ['traffic'] : []
    const tabs: MonitoringTab[] = []
    if (logsDashboardEnabled) tabs.push('connections', 'services')
    if (trafficSyncEnabled) tabs.push('traffic')
    if (logsDashboardEnabled || serverMonitorEnabled) tabs.push('resources')
    if (logsDashboardEnabled || actionLogsEnabled) tabs.push('logs')
    return tabs
  }, [isAdmin, logsDashboardEnabled, trafficSyncEnabled, serverMonitorEnabled, actionLogsEnabled])

  const [tab, setTab] = usePageTab<MonitoringTab>({ tabs: availableTabs })

  const resourceChipOptions = useMemo<SegmentOption<ResourceScopeTab>[]>(() => {
    const options: SegmentOption<ResourceScopeTab>[] = []
    if (logsDashboardEnabled) {
      options.push({ id: 'node', label: 'Узел', icon: Server })
      options.push({ id: 'panel', label: 'Панель', icon: LayoutDashboard })
    }
    if (serverMonitorEnabled) options.push({ id: 'host', label: 'Хост', icon: Cpu })
    return options
  }, [logsDashboardEnabled, serverMonitorEnabled])

  const [resourceScope, setResourceScope] = usePageTab<ResourceScopeTab>({
    tabs: resourceChipOptions.map((option) => option.id),
    param: 'scope',
  })

  /** Подключения и «Службы» — это прежний NOC: данные, лента событий и шапка с автообновлением. */
  const nocActive = tab === 'connections' || tab === 'services'
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const { startGlobal, doneGlobal } = useProgress()
  const [scope, setScope] = useState<MonitoringScope>(() => storage.readChoice('scope', ['node', 'all'] as const) ?? 'node')
  const [scopeInitialized, setScopeInitialized] = useState(() => storage.readChoice('scope', ['node', 'all'] as const) != null)
  const [haMode, setHaMode] = useState<'dedupe' | 'raw'>(
    () => storage.readChoice('haMode', ['dedupe', 'raw'] as const) ?? 'dedupe',
  )
  const [data, setData] = useState<MonitoringOverview | null>(null)
  const [incidents, setIncidents] = useState<NocIncidentItem[]>([])
  const [connectionHistory, setConnectionHistory] = useState<ConnectionHistoryResponse | null>(null)
  const [connectionHistoryPeriod, setConnectionHistoryPeriod] = useState<'1h' | '6h' | '24h'>('1h')
  const [connectionHistoryLoading, setConnectionHistoryLoading] = useState(false)
  const [liveLoading, setLiveLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const [search, setSearch] = useState('')
  const [connectionsView, setConnectionsView] = useState<ConnectionsViewMode>(
    () => storage.readChoice('connectionsView', ['configs', 'users'] as const) ?? 'configs',
  )
  const [onlineOnly, setOnlineOnly] = useState(() => storage.readChoice('onlineOnly', ['true', 'false'] as const) !== 'false')
  const [protocolFilter, setProtocolFilter] = useState<ProtocolFilter>(
    () => storage.readChoice('protocol', PROTOCOL_FILTER_VALUES) ?? 'all',
  )
  const [filterNode, setFilterNode] = useState(() => storage.read('filterNode') || '')
  const [filterCity, setFilterCity] = useState(() => storage.read('filterCity') || '')
  const [filterIsp, setFilterIsp] = useState(() => storage.read('filterIsp') || '')
  const [minDuration, setMinDuration] = useState<MinDurationFilter>(
    () => storage.readChoice('minDuration', ['any', '15m', '1h', '4h'] as const) ?? 'any',
  )
  const [sortKey, setSortKey] = useState<NocSortKey>(
    () => storage.readChoice('sortKey', ['client', 'traffic', 'time', 'rate', 'duration'] as const) ?? 'traffic',
  )
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>(
    () => storage.readChoice('sortDir', ['asc', 'desc'] as const) ?? 'desc',
  )
  const [restartingService, setRestartingService] = useState<string | null>(null)
  const [resourcePeriod, setResourcePeriod] = useState<'1d' | '7d' | '30d'>('1d')
  const [panelResourcePeriod, setPanelResourcePeriod] = useState<'1d' | '7d' | '30d'>('1d')
  const [resourceHistory, setResourceHistory] = useState<ResourceHistory | null>(null)
  const [resourceLoading, setResourceLoading] = useState(false)
  const loadRef = useRef<(opts?: { initial?: boolean; manual?: boolean }) => Promise<void>>()
  const lastIncidentsAtRef = useRef(0)
  const activeNodeIdRef = useRef(activeNode?.id)
  activeNodeIdRef.current = activeNode?.id
  // Service incidents come from the server-side active node, so a node switch makes the list stale.
  const incidentsNodeIdRef = useRef<number | undefined>(undefined)
  const incidentsInFlightRef = useRef<Promise<void> | null>(null)

  const refreshIncidents = useCallback((opts: { force?: boolean } = {}) => {
    const { force = false } = opts
    const nodeId = activeNodeIdRef.current
    const sameNode = incidentsNodeIdRef.current === nodeId
    if (incidentsInFlightRef.current && sameNode) return incidentsInFlightRef.current
    const now = Date.now()
    if (!force && sameNode && now - lastIncidentsAtRef.current < INCIDENTS_REFRESH_INTERVAL_MS) {
      return Promise.resolve()
    }
    lastIncidentsAtRef.current = now
    incidentsNodeIdRef.current = nodeId
    const request: Promise<void> = getNocIncidents(20)
      .then(
        (resp) => {
          if (incidentsInFlightRef.current === request) setIncidents(resp.items)
        },
        () => {
          /* keep previous */
        },
      )
      .finally(() => {
        if (incidentsInFlightRef.current === request) incidentsInFlightRef.current = null
      })
    incidentsInFlightRef.current = request
    return request
  }, [])

  const loadConnectionHistory = useCallback(async (period: '1h' | '6h' | '24h', historyScope: MonitoringScope) => {
    setConnectionHistoryLoading(true)
    try {
      setConnectionHistory(await getConnectionHistory(period, historyScope))
    } catch {
      /* chart falls back to live tail */
    } finally {
      setConnectionHistoryLoading(false)
    }
  }, [])

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
        setData(await getMonitoring(scope, haMode))
        setLoadError(null)
        void refreshIncidents({ force: manual })
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
    [startGlobal, doneGlobal, success, notifyError, scope, haMode, refreshIncidents],
  )

  loadRef.current = load

  useEffect(() => {
    if (nodesLoading || scopeInitialized) return
    if (nodes.length > 1) setScope('all')
    setScopeInitialized(true)
  }, [nodesLoading, nodes.length, scopeInitialized])

  useEffect(() => {
    if (scopeInitialized) storage.write('scope', scope)
  }, [scope, scopeInitialized])

  useEffect(() => {
    storage.write('onlineOnly', String(onlineOnly))
  }, [onlineOnly])

  useEffect(() => {
    storage.write('protocol', protocolFilter)
  }, [protocolFilter])

  useEffect(() => {
    if (!awg2Enabled && protocolFilter === 'amneziawg2') {
      setProtocolFilter('all')
    }
  }, [awg2Enabled, protocolFilter])

  useEffect(() => {
    storage.write('haMode', haMode)
  }, [haMode])

  useEffect(() => {
    storage.write('filterNode', filterNode)
  }, [filterNode])

  useEffect(() => {
    storage.write('filterCity', filterCity)
  }, [filterCity])

  useEffect(() => {
    storage.write('filterIsp', filterIsp)
  }, [filterIsp])

  useEffect(() => {
    storage.write('minDuration', minDuration)
  }, [minDuration])

  useEffect(() => {
    storage.write('sortKey', sortKey)
  }, [sortKey])

  useEffect(() => {
    storage.write('sortDir', sortDir)
  }, [sortDir])

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

  const scopeReady = !nodeLoading && scopeInitialized

  useEffect(() => {
    if (!scopeReady || !nocActive) return
    load({ initial: true })
  }, [load, activeNode?.id, scope, haMode, scopeReady, nocActive])

  useEffect(() => {
    if (nodeLoading) return
    if (tab !== 'resources' || resourceScope !== 'node') return
    loadResourceHistory(resourcePeriod)
  }, [loadResourceHistory, nodeLoading, activeNode?.id, resourcePeriod, tab, resourceScope])

  useEffect(() => {
    if (!scopeReady || !nocActive) return
    void loadConnectionHistory(connectionHistoryPeriod, scope)
  }, [loadConnectionHistory, connectionHistoryPeriod, scope, scopeReady, activeNode?.id, nocActive])

  useEffect(() => {
    if (!autoRefresh || !scopeReady || !nocActive) return

    let stream: StreamHandle | null = null
    let tick: ReturnType<typeof setInterval> | undefined

    const disconnect = () => {
      stream?.close()
      stream = null
      if (tick !== undefined) {
        clearInterval(tick)
        tick = undefined
      }
    }

    const connect = () => {
      disconnect()
      stream = openMonitoringStream(
        (payload) => {
          setData(payload)
          setLoadError(null)
          setCountdown(REFRESH_INTERVAL)
          void refreshIncidents()
        },
        () => {},
        scope,
        haMode,
      )
      tick = setInterval(() => {
        if (isDocumentHidden()) return
        setCountdown((c) => (c <= 1 ? REFRESH_INTERVAL : c - 1))
      }, 1000)
    }

    const onVisibility = () => {
      if (isDocumentHidden()) {
        disconnect()
        return
      }
      connect()
    }

    if (typeof document === 'undefined' || !isDocumentHidden()) {
      connect()
    }
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [autoRefresh, scopeReady, scope, haMode, activeNode?.id, refreshIncidents, nocActive])

  const isFederated = scope === 'all' || data?.scope === 'all'
  const showNodeColumn = isFederated
  const hasMultipleNodes = nodes.length > 1

  const nodeOffline = activeNode?.status === 'offline'
  const nodeUnknown = activeNode?.status === 'unknown'

  const openvpnClients = data?.openvpn_clients ?? []
  const wireguardPeers = data?.wireguard_peers ?? []
  const amneziawg2Peers = awg2Enabled ? (data?.amneziawg2_peers ?? []) : []
  const wgActive = wireguardPeers.filter(isWireGuardOnline).length
  const awg2Active = amneziawg2Peers.filter(isWireGuardOnline).length
  const totalConnections = openvpnClients.length + wgActive + awg2Active
  const activeServices = data?.services.filter((s) => s.active).length ?? 0
  const totalServices = data?.services.length ?? 0

  const searchQuery = search.trim().toLowerCase()

  useEffect(() => {
    storage.write('connectionsView', connectionsView)
  }, [connectionsView])

  const matchesWgPeerSearch = useCallback(
    (p: (typeof wireguardPeers)[number]) => {
      if (!searchQuery) return true
      const name = (p.client_name ?? '').toLowerCase()
      const address = getConnectionDisplayAddress(p, 'endpoint').toLowerCase()
      const geo = (getConnectionGeoLabel(p) || '').toLowerCase()
      return (
        name.includes(searchQuery) ||
        address.includes(searchQuery) ||
        geo.includes(searchQuery) ||
        (p.owner_username ?? '').toLowerCase().includes(searchQuery) ||
        (p.endpoint ?? '').toLowerCase().includes(searchQuery) ||
        (p.allowed_ips ?? '').toLowerCase().includes(searchQuery) ||
        p.interface.toLowerCase().includes(searchQuery) ||
        p.public_key.toLowerCase().includes(searchQuery) ||
        (p.node_name || '').toLowerCase().includes(searchQuery) ||
        (p.ha?.shared_domain || '').toLowerCase().includes(searchQuery)
      )
    },
    [searchQuery],
  )

  const filteredOpenVpn = useMemo(() => {
    if (!searchQuery) return openvpnClients
    return openvpnClients.filter((c) => {
      const address = getConnectionDisplayAddress(c).toLowerCase()
      const geo = (getConnectionGeoLabel(c) || '').toLowerCase()
      return (
        c.common_name.toLowerCase().includes(searchQuery) ||
        address.includes(searchQuery) ||
        geo.includes(searchQuery) ||
        (c.owner_username ?? '').toLowerCase().includes(searchQuery) ||
        c.virtual_address.toLowerCase().includes(searchQuery) ||
        (c.node_name || '').toLowerCase().includes(searchQuery) ||
        (c.ha?.shared_domain || '').toLowerCase().includes(searchQuery)
      )
    })
  }, [openvpnClients, searchQuery])

  const filteredWireGuard = useMemo(() => {
    if (!searchQuery) return wireguardPeers
    return wireguardPeers.filter(matchesWgPeerSearch)
  }, [wireguardPeers, searchQuery, matchesWgPeerSearch])

  const filteredAmneziaWg2 = useMemo(() => {
    if (!searchQuery) return amneziawg2Peers
    return amneziawg2Peers.filter(matchesWgPeerSearch)
  }, [amneziawg2Peers, searchQuery, matchesWgPeerSearch])

  const visibleWireGuard = useMemo(() => {
    if (!onlineOnly) return filteredWireGuard
    return filteredWireGuard.filter(isWireGuardOnline)
  }, [filteredWireGuard, onlineOnly])

  const visibleAmneziaWg2 = useMemo(() => {
    if (!onlineOnly) return filteredAmneziaWg2
    return filteredAmneziaWg2.filter(isWireGuardOnline)
  }, [filteredAmneziaWg2, onlineOnly])

  const showOpenVpn = protocolFilter === 'all' || protocolFilter === 'openvpn'
  const showWireGuard = protocolFilter === 'all' || protocolFilter === 'wireguard'
  const showAmneziaWg2 =
    awg2Enabled && (protocolFilter === 'all' || protocolFilter === 'amneziawg2')
  const visibleOpenVpn = showOpenVpn ? filteredOpenVpn : []
  const visibleWireGuardList = showWireGuard ? visibleWireGuard : []
  const visibleAmneziaWg2List = showAmneziaWg2 ? visibleAmneziaWg2 : []
  const visibleCount =
    visibleOpenVpn.length + visibleWireGuardList.length + visibleAmneziaWg2List.length
  const filteredTotalCount =
    (showOpenVpn ? filteredOpenVpn.length : 0) +
    (showWireGuard ? filteredWireGuard.length : 0) +
    (showAmneziaWg2 ? filteredAmneziaWg2.length : 0)
  const hasFilteredClients = visibleCount > 0

  const baseConnectionRows = useMemo(
    () =>
      buildMonitoringConnectionRows(visibleOpenVpn, visibleWireGuardList, {
        showOpenVpn,
        showWireGuard,
        isWireGuardOnline,
        amneziawg2Peers: visibleAmneziaWg2List,
        showAmneziaWg2,
        isAwg2Online: isWireGuardOnline,
      }),
    [
      visibleOpenVpn,
      visibleWireGuardList,
      visibleAmneziaWg2List,
      showOpenVpn,
      showWireGuard,
      showAmneziaWg2,
    ],
  )

  const rates = useConnectionRates(baseConnectionRows, data?.timestamp)

  const connectionRows = useMemo(() => {
    const minSec = minDurationSeconds(minDuration)
    return baseConnectionRows
      .map((row) => {
        const rate = rates.get(row.key)
        return {
          ...row,
          rxBps: rate?.rxBps ?? null,
          txBps: rate?.txBps ?? null,
          ratePending: rate?.pending ?? true,
        }
      })
      .filter((row) => {
        if (filterNode) {
          const nodeLabel = row.activeNodeName || row.nodeName || ''
          if (nodeLabel !== filterNode) return false
        }
        if (filterCity === NOC_FILTER_NONE) {
          if (row.city) return false
        } else if (filterCity && (row.city || '') !== filterCity) {
          return false
        }
        if (filterIsp === NOC_FILTER_NONE) {
          if (row.isp) return false
        } else if (filterIsp && (row.isp || '') !== filterIsp) {
          return false
        }
        if (minSec != null && (row.durationSec == null || row.durationSec < minSec)) return false
        return true
      })
  }, [baseConnectionRows, rates, filterNode, filterCity, filterIsp, minDuration])

  const connectionUserGroups = useMemo(
    () => (connectionsView === 'users' ? groupConnectionsByOwner(connectionRows) : []),
    [connectionsView, connectionRows],
  )
  const onlineUserGroupsCount = useMemo(
    () => connectionUserGroups.filter((group) => group.onlineCount > 0).length,
    [connectionUserGroups],
  )

  const nodeFilterOptions = useMemo(() => {
    const names = new Set<string>()
    for (const row of baseConnectionRows) {
      const name = row.activeNodeName || row.nodeName
      if (name) names.add(name)
    }
    for (const node of data?.nodes_summary ?? []) names.add(node.node_name)
    return [...names].sort((a, b) => a.localeCompare(b))
  }, [baseConnectionRows, data?.nodes_summary])

  const cityFilterOptions = useMemo(() => {
    const names = new Set<string>()
    for (const row of baseConnectionRows) {
      if (row.city) names.add(row.city)
    }
    return [...names].sort((a, b) => a.localeCompare(b))
  }, [baseConnectionRows])

  const ispFilterOptions = useMemo(() => {
    const names = new Set<string>()
    for (const row of baseConnectionRows) {
      if (row.isp) names.add(row.isp)
    }
    return [...names].sort((a, b) => a.localeCompare(b))
  }, [baseConnectionRows])

  const handleRefresh = () => {
    load({ manual: true })
    loadResourceHistory(resourcePeriod)
    void loadConnectionHistory(connectionHistoryPeriod, scope)
  }

  const handleDisconnectOpenVpn = (clientName: string) => {
    confirm({
      title: 'Отключить OpenVPN-сессию?',
      description: `Клиент «${clientName}» будет отключён от VPN.`,
      confirmLabel: 'Отключить',
      destructive: true,
      onConfirm: async () => {
        try {
          await openvpnDisconnect(clientName)
          success(`Клиент ${clientName} отключён`)
          await load({ manual: false })
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка отключения')
        }
      },
    })
  }

  const handleDisconnectDevice = (target: DeviceDisconnectTarget, blockMinutes?: number) => {
    const blocking = blockMinutes != null
    confirm({
      title: blocking ? `Отключить и заблокировать на ${blockMinutes} мин?` : 'Отключить одно устройство?',
      description: blocking
        ? `Сессия Client ID ${target.clientId} (${target.profile}) будет отключена, а клиент «${target.clientName}» заблокирован на ${blockMinutes} мин — все его устройства не смогут подключиться до истечения срока.`
        : `Сессия Client ID ${target.clientId} (${target.profile}) будет отключена. Остальные устройства клиента останутся на связи.`,
      confirmLabel: blocking ? 'Отключить и заблокировать' : 'Отключить устройство',
      destructive: true,
      onConfirm: async () => {
        try {
          await openvpnDisconnectSession(target.profile, target.clientId, target.nodeId, {
            clientName: target.clientName,
            blockMinutes,
          })
          success(
            blocking
              ? `Устройство ${target.clientId} отключено, «${target.clientName}» заблокирован на ${blockMinutes} мин`
              : `Устройство ${target.clientId} отключено`,
          )
          await load({ manual: false })
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка отключения устройства')
        }
      },
    })
  }

  const handleRestartService = (serviceName: string) => {
    confirm({
      title: 'Перезапустить службу?',
      description: `Служба «${serviceName}» будет перезапущена на активном узле. Критические VPN-службы могут разорвать сессии клиентов.`,
      alert: {
        variant: 'warning',
        title: 'Возможен обрыв сессий',
        children: 'Подтвердите только если понимаете последствия.',
      },
      confirmLabel: 'Перезапустить',
      destructive: true,
      onConfirm: async () => {
        setRestartingService(serviceName)
        try {
          const resp = await restartService(serviceName)
          success(resp.message || `Служба ${serviceName} перезапущена`)
          await load({ manual: false })
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка перезапуска')
        } finally {
          setRestartingService(null)
        }
      },
    })
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
    const levelRank = (level?: string) =>
      level === 'critical' ? 0 : level === 'warn' ? 1 : level === 'ok' ? 2 : 3
    const statusRank = (status: string) => (status === 'online' ? 2 : status === 'offline' ? 0 : 1)
    return [...list].sort((a, b) => {
      const byLevel = levelRank(a.health_level) - levelRank(b.health_level)
      if (byLevel !== 0) return byLevel
      const byStatus = statusRank(a.status) - statusRank(b.status)
      if (byStatus !== 0) return byStatus
      return a.node_name.localeCompare(b.node_name)
    })
  }, [data?.nodes_summary])

  const compareMetricRows = useMemo(
    () => [
      { key: 'status', label: 'Статус' },
      {
        key: 'vpn',
        label: awg2Enabled ? 'Online OVPN / WG / AWG 2.0' : 'Online OVPN / WG',
      },
      { key: 'services', label: 'Службы active/total' },
      { key: 'cpu', label: 'CPU' },
      { key: 'ram', label: 'RAM' },
      { key: 'traffic', label: 'Трафик (всего)' },
      { key: 'cidr', label: 'CIDR маршруты' },
    ],
    [awg2Enabled],
  )

  if (availableTabs.length === 0) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="space-y-6">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <PageSectionHeader
        icon={Radio}
        title="Наблюдение"
        docsHref={TAB_META[tab].docsHref}
        titleAddon={
          <NodeBadge
            name={
              nocActive && isFederated
                ? `Все узлы (${data?.nodes_online ?? 0}/${data?.nodes_total ?? nodes.length})`
                : (activeNode?.name ?? data?.node_name)
            }
            status={nocActive && isFederated ? 'online' : activeNode?.status}
          />
        }
        description={
          nocActive ? (
            <div className="space-y-1">
              <div>
                {isFederated
                  ? 'Сводка активных VPN-подключений со всех узлов'
                  : awg2Enabled
                    ? 'Активные VPN-подключения OpenVPN, WireGuard и AWG 2.0 в реальном времени'
                    : 'Активные VPN-подключения OpenVPN и WireGuard в реальном времени'}
                {data?.timestamp && <> · обновлено {formatDateTime(data.timestamp)}</>}
              </div>
              <NocDataFreshness
                timestamp={data?.timestamp}
                refreshIntervalSec={REFRESH_INTERVAL}
                geoipMode={data?.geoip_mode}
                dataSource={data?.openvpn_data_source}
                globalStats={data?.openvpn_global_stats}
                servedFromCache={data?.served_from_cache}
              />
            </div>
          ) : (
            TAB_META[tab].description
          )
        }
        actions={
          nocActive ? (
            <>
              {hasMultipleNodes && (
                <ChipSegments
                  ariaLabel="Охват мониторинга"
                  value={scope}
                  onChange={setScope}
                  options={[
                    { id: 'node', label: 'Активный узел', icon: Server },
                    {
                      id: 'all',
                      label: 'Все узлы',
                      icon: Globe,
                      hint: (
                        <span className="ml-0.5 rounded bg-primary/10 px-1 text-[10px] font-semibold tabular-nums text-primary">
                          {data?.nodes_online ?? 0}/{data?.nodes_total ?? nodes.length}
                        </span>
                      ),
                    },
                  ]}
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
          ) : undefined
        }
      />

      <Tabs value={tab} onValueChange={(next) => setTab(next as MonitoringTab)} className="space-y-4">
        {availableTabs.length > 1 && (
          <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1">
            {availableTabs.map((id) => {
              const meta = TAB_META[id]
              const Icon = meta.icon
              return (
                <TabsTrigger key={id} value={id} className="gap-1.5">
                  <Icon size={14} />
                  {meta.label}
                  {id === 'connections' && totalConnections > 0 && (
                    <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                      {totalConnections}
                    </Badge>
                  )}
                  {id === 'services' && totalServices > 0 && (
                    <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                      {activeServices}/{totalServices}
                    </Badge>
                  )}
                </TabsTrigger>
              )
            })}
          </TabsList>
        )}

        {nocActive && (
          <TabsContent value={tab} className="space-y-4">
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

            <NocIncidentFeed items={incidents} />

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
                    {isFederated && (
                      <div className="ml-auto flex items-center gap-2">
                        <Switch
                          id="noc-ha-raw"
                          checked={haMode === 'raw'}
                          onCheckedChange={(checked) => setHaMode(checked ? 'raw' : 'dedupe')}
                        />
                        <Label htmlFor="noc-ha-raw" className="text-xs text-muted-foreground">
                          Показать по узлам
                        </Label>
                      </div>
                    )}
                  </div>

                  {isFederated && (data.nodes_summary?.length ?? 0) > 0 && (
                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="flex items-center gap-2 text-base">
                          <Server size={18} />
                          Сводка по узлам
                        </CardTitle>
                        <CardDescription>
                          Нажмите на узел, чтобы открыть его детально
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="pt-0">
                        <Tabs defaultValue="summary" className="space-y-3">
                          <TabsList className="h-8">
                            <TabsTrigger value="summary" className="text-xs">
                              Сводка
                            </TabsTrigger>
                            {hasMultipleNodes && (
                              <TabsTrigger value="compare" className="text-xs">
                                Сравнение
                              </TabsTrigger>
                            )}
                          </TabsList>
                          <TabsContent value="summary" className="mt-0">
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
                                <Table className="w-full table-fixed" containerClassName="w-full">
                                  <TableHeader>
                                    <TableRow className="hover:bg-transparent">
                                      <TableHead className="h-9 w-[18%] whitespace-nowrap px-3">Узел</TableHead>
                                      <TableHead className="h-9 w-[11%] whitespace-nowrap px-3">Статус</TableHead>
                                      <TableHead className="h-9 w-[7%] whitespace-nowrap px-3 text-center">Health</TableHead>
                                      <TableHead className="h-9 w-[6%] whitespace-nowrap px-3 text-right">OVPN</TableHead>
                                      <TableHead className="h-9 w-[6%] whitespace-nowrap px-3 text-right">WG</TableHead>
                                      {awg2Enabled && (
                                        <TableHead className="h-9 w-[7%] whitespace-nowrap px-3 text-right">
                                          AWG 2.0
                                        </TableHead>
                                      )}
                                      <TableHead className="h-9 w-[7%] whitespace-nowrap px-3 text-right">Службы</TableHead>
                                      <TableHead className="h-9 w-[15%] whitespace-nowrap px-3">CPU</TableHead>
                                      <TableHead className="h-9 w-[15%] whitespace-nowrap px-3">RAM</TableHead>
                                      <TableHead className="h-9 w-[9%] whitespace-nowrap px-3 text-right">Трафик</TableHead>
                                      <TableHead className="h-9 w-[6%] whitespace-nowrap px-3 text-right">CIDR</TableHead>
                                    </TableRow>
                                  </TableHeader>
                                  <TableBody>
                                    {sortedNodeSummary.map((node: MonitoringNodeSummary) => {
                                      const isActive = node.node_id === activeNode?.id
                                      const servicesIncomplete =
                                        node.total_services > 0 && node.active_services < node.total_services
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
                                          <TableCell className="whitespace-nowrap px-3 py-2.5 font-medium">
                                            <span className="inline-flex min-w-0 max-w-full items-center gap-1.5">
                                              <ChevronRight
                                                size={14}
                                                className="shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
                                              />
                                              <span className="truncate">{node.node_name}</span>
                                              {isActive && (
                                                <span
                                                  className="size-1.5 shrink-0 rounded-full bg-primary"
                                                  title="Активный узел"
                                                  aria-label="Активный узел"
                                                />
                                              )}
                                            </span>
                                          </TableCell>
                                          <TableCell className="whitespace-nowrap px-3 py-2.5">
                                            <NodeStatusBadge status={node.status as NodeStatus} />
                                            {node.error && (
                                              <p
                                                className="mt-1 max-w-full truncate text-[11px] text-destructive"
                                                title={node.error}
                                              >
                                                {node.error}
                                              </p>
                                            )}
                                          </TableCell>
                                          <TableCell className="px-3 py-2.5 text-center">
                                            <HealthScoreBadge score={node.health_score} level={node.health_level} />
                                          </TableCell>
                                          <TableCell className="px-3 py-2.5 text-right font-mono text-xs tabular-nums">
                                            {node.connected_openvpn}
                                          </TableCell>
                                          <TableCell className="px-3 py-2.5 text-right font-mono text-xs tabular-nums">
                                            {node.connected_wireguard}
                                          </TableCell>
                                          {awg2Enabled && (
                                            <TableCell className="px-3 py-2.5 text-right font-mono text-xs tabular-nums">
                                              {node.connected_amneziawg2 ?? 0}
                                            </TableCell>
                                          )}
                                          <TableCell
                                            className={cn(
                                              'px-3 py-2.5 text-right font-mono text-xs tabular-nums',
                                              servicesIncomplete && 'text-amber-600 dark:text-amber-400',
                                            )}
                                          >
                                            {node.active_services}
                                            <span className="text-muted-foreground">/{node.total_services}</span>
                                          </TableCell>
                                          <TableCell className="px-3 py-2.5">
                                            <ResourceMetricInline
                                              value={node.cpu_percent}
                                              label={`CPU ${node.node_name}`}
                                              barClassName="w-full max-w-[9rem]"
                                            />
                                          </TableCell>
                                          <TableCell className="px-3 py-2.5">
                                            <ResourceMetricInline
                                              value={node.memory_percent}
                                              label={`RAM ${node.node_name}`}
                                              barClassName="w-full max-w-[9rem]"
                                            />
                                          </TableCell>
                                          <TableCell className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-xs tabular-nums">
                                            {node.total_traffic_bytes != null
                                              ? formatBytes(node.total_traffic_bytes)
                                              : '—'}
                                          </TableCell>
                                          <TableCell className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-xs tabular-nums">
                                            {node.cidr_routes_count ?? '—'}
                                          </TableCell>
                                        </TableRow>
                                      )
                                    })}
                                  </TableBody>
                                </Table>
                              }
                              mobileClassName="space-y-3"
                              desktopClassName="w-full overflow-x-auto rounded-md border"
                            />
                          </TabsContent>
                          {hasMultipleNodes && (
                            <TabsContent value="compare" className="mt-0">
                              <div className="w-full overflow-x-auto rounded-md border">
                                <Table className="w-full" containerClassName="w-full">
                                  <TableHeader>
                                    <TableRow>
                                      <TableHead className="w-[20%] whitespace-nowrap px-3">Метрика</TableHead>
                                      {sortedNodeSummary.map((node) => (
                                        <TableHead
                                          key={node.node_id}
                                          className="whitespace-nowrap px-3 text-center"
                                        >
                                          <div className="flex flex-col items-center gap-1">
                                            <span className="font-medium">{node.node_name}</span>
                                            <NodeStatusBadge status={node.status as NodeStatus} showLabel={false} />
                                          </div>
                                        </TableHead>
                                      ))}
                                    </TableRow>
                                  </TableHeader>
                                  <TableBody>
                                    {compareMetricRows.map((metric) => (
                                      <TableRow key={metric.key}>
                                        <TableCell className="px-3 py-2.5 text-xs font-medium text-muted-foreground">
                                          {metric.label}
                                        </TableCell>
                                        {sortedNodeSummary.map((node) => (
                                          <TableCell key={`${metric.key}-${node.node_id}`} className="px-3 py-2.5 text-center">
                                            {metric.key === 'status' ? (
                                              <NodeStatusBadge status={node.status as NodeStatus} />
                                            ) : metric.key === 'vpn' ? (
                                              <span className="font-mono text-xs">
                                                {awg2Enabled
                                                  ? `${node.connected_openvpn} / ${node.connected_wireguard} / ${node.connected_amneziawg2 ?? 0}`
                                                  : `${node.connected_openvpn} / ${node.connected_wireguard}`}
                                              </span>
                                            ) : metric.key === 'services' ? (
                                              <span className="font-mono text-xs">
                                                {node.active_services}/{node.total_services}
                                              </span>
                                            ) : metric.key === 'cpu' ? (
                                              <div className="mx-auto max-w-[12rem]">
                                                <ResourceMetricInline
                                                  value={node.cpu_percent}
                                                  label={`CPU ${node.node_name}`}
                                                  barClassName="w-full"
                                                  className="justify-center"
                                                />
                                              </div>
                                            ) : metric.key === 'ram' ? (
                                              <div className="mx-auto max-w-[12rem]">
                                                <ResourceMetricInline
                                                  value={node.memory_percent}
                                                  label={`RAM ${node.node_name}`}
                                                  barClassName="w-full"
                                                  className="justify-center"
                                                />
                                              </div>
                                            ) : metric.key === 'traffic' ? (
                                              <span className="font-mono text-xs">
                                                {node.total_traffic_bytes != null ? formatBytes(node.total_traffic_bytes) : '—'}
                                              </span>
                                            ) : (
                                              <span className="font-mono text-xs">{node.cidr_routes_count ?? '—'}</span>
                                            )}
                                          </TableCell>
                                        ))}
                                      </TableRow>
                                    ))}
                                  </TableBody>
                                </Table>
                              </div>
                            </TabsContent>
                          )}
                        </Tabs>
                      </CardContent>
                    </Card>
                  )}

                  <div className={cn('grid gap-4 sm:grid-cols-2', awg2Enabled ? 'xl:grid-cols-5' : 'xl:grid-cols-4')}>
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
                    {awg2Enabled && (
                      <SummaryCard
                        label="AWG 2.0 онлайн"
                        value={String(
                          isFederated ? data.total_connected_amneziawg2 ?? awg2Active : awg2Active,
                        )}
                        icon={Radio}
                        accent="text-amber-500"
                        sub={`из ${amneziawg2Peers.length} пиров`}
                      />
                    )}
                    <SummaryCard
                      label="Всего подключено"
                      value={String(totalConnections)}
                      icon={Users}
                      sub={
                        awg2Enabled
                          ? `OVPN ${openvpnClients.length} · WG ${wgActive} · AWG 2.0 ${awg2Active}`
                          : `OVPN ${openvpnClients.length} · WG ${wgActive}`
                      }
                    />
                    <SummaryCard
                      label="Трафик сессий"
                      value={formatBytes(totalTraffic(data))}
                      icon={Activity}
                      sub={`RX ${formatBytes(
                        openvpnClients.reduce((s, c) => s + c.bytes_received, 0) +
                          wireguardPeers.reduce((s, p) => s + p.transfer_rx, 0) +
                          amneziawg2Peers.reduce((s, p) => s + p.transfer_rx, 0),
                      )} · TX ${formatBytes(
                        openvpnClients.reduce((s, c) => s + c.bytes_sent, 0) +
                          wireguardPeers.reduce((s, p) => s + p.transfer_tx, 0) +
                          amneziawg2Peers.reduce((s, p) => s + p.transfer_tx, 0),
                      )}`}
                    />
                  </div>

                  <div className="space-y-4">
                    <Suspense fallback={<ChartFallback />}>
                      <MonitoringCharts
                        data={data}
                        serverHistory={connectionHistory?.points}
                        historyPeriod={connectionHistoryPeriod}
                        onHistoryPeriodChange={setConnectionHistoryPeriod}
                        historyLoading={connectionHistoryLoading}
                      />
                    </Suspense>
                    {totalConnections > 0 && hasFilteredClients && (
                      <Suspense fallback={<ChartFallback />}>
                        <MonitoringGeoSummary
                          openvpnClients={visibleOpenVpn}
                          wireguardPeers={visibleWireGuardList}
                          showOpenVpn={showOpenVpn}
                          showWireGuard={showWireGuard}
                          isWireGuardOnline={isWireGuardOnline}
                          onlineOnly={onlineOnly}
                          amneziawg2Peers={visibleAmneziaWg2List}
                          showAmneziaWg2={showAmneziaWg2}
                        />
                      </Suspense>
                    )}
                  </div>

                  {tab === 'connections' ? (
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
                                : connectionsView === 'users'
                                  ? `${connectionUserGroups.length} пользователей · ${onlineUserGroupsCount} онлайн · ${visibleCount} подключений`
                                  : onlineOnly
                                    ? `${visibleCount} онлайн${filteredTotalCount > visibleCount ? ` из ${filteredTotalCount}` : ''}`
                                    : `${visibleCount} из ${openvpnClients.length + wireguardPeers.length + amneziawg2Peers.length} записей`}
                            </CardDescription>
                          </div>
                          <div className="flex w-full flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center lg:w-auto lg:justify-end">
                            <ViewModeToggle
                              value={connectionsView}
                              onChange={setConnectionsView}
                              ariaLabel="Группировка VPN-подключений"
                              options={[
                                { value: 'configs', label: 'Конфиги', icon: Server },
                                { value: 'users', label: 'Пользователи', icon: Users },
                              ]}
                            />
                            <div className="relative w-full sm:w-56">
                              <Search
                                size={14}
                                className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                              />
                              <Input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Поиск по имени, пользователю, IP, городу..."
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
                                {awg2Enabled && <SelectItem value="amneziawg2">AWG 2.0</SelectItem>}
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
                        <CardContent className="space-y-4">
                          <NocConnectionFilters
                            className="w-full"
                            showNodeFilter={isFederated}
                            filterNode={filterNode}
                            filterCity={filterCity}
                            filterIsp={filterIsp}
                            minDuration={minDuration}
                            sortKey={sortKey}
                            nodeOptions={nodeFilterOptions}
                            cityOptions={cityFilterOptions}
                            ispOptions={ispFilterOptions}
                            onFilterNode={setFilterNode}
                            onFilterCity={setFilterCity}
                            onFilterIsp={setFilterIsp}
                            onMinDuration={setMinDuration}
                            onSortKey={(key) => {
                              setSortKey(key)
                              setSortDir(key === 'client' ? 'asc' : 'desc')
                            }}
                          />
                          {totalConnections === 0 ? (
                            <EmptyState
                              icon={WifiOff}
                              title="Нет подключённых клиентов"
                              description="Активные VPN-сессии появятся здесь после подключения пользователей"
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
                          ) : connectionsView === 'users' ? (
                            <MonitoringUsersList
                              rows={connectionRows}
                              showNodeColumn={showNodeColumn}
                              onDisconnectOpenVpn={handleDisconnectOpenVpn}
                              onDisconnectDevice={handleDisconnectDevice}
                            />
                          ) : (
                            <MonitoringConnectionsList
                              rows={connectionRows}
                              showNodeColumn={showNodeColumn}
                              sortKey={sortKey}
                              sortDir={sortDir}
                              onSortChange={(key, dir) => {
                                setSortKey(key)
                                setSortDir(dir)
                              }}
                              onDisconnectOpenVpn={handleDisconnectOpenVpn}
                              onDisconnectDevice={handleDisconnectDevice}
                            />
                          )}
                        </CardContent>
                      </Card>
                  ) : (
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
                            <ServiceMatrix
                              services={data.services}
                              allowRestart={!isFederated}
                              onRestart={handleRestartService}
                              restartingName={restartingService}
                            />
                          )}
                        </CardContent>
                      </Card>
                  )}
                </>
              )
            )}
          </TabsContent>
        )}

        {availableTabs.includes('traffic') && (
          <TabsContent value="traffic" className="space-y-4">
            <Suspense fallback={<Spinner label="Загрузка статистики трафика..." className="py-16" />}>
              <TrafficPage embedded />
            </Suspense>
          </TabsContent>
        )}

        {availableTabs.includes('resources') && (
          <TabsContent value="resources" className="space-y-4">
            {resourceChipOptions.length > 1 && (
              <ChipSegments
                ariaLabel="Область ресурсов"
                value={resourceScope}
                onChange={setResourceScope}
                options={resourceChipOptions}
              />
            )}
            {resourceScope === 'node' && (
              <>
                <SettingsAlert variant="info" title="Ресурсы VPN-узла, не панели">
                  История CPU/RAM/диска относится к серверу AntiZapret (VPN, маршрутизация, службы), с которого
                  собираются данные. Снимки пишет панель с активного узла{' '}
                  <strong>{activeNode?.name ?? data?.node_name ?? '—'}</strong> каждые ~60 с. Для live-метрик
                  переключитесь на чип «Хост».
                </SettingsAlert>
                <Suspense fallback={<ChartFallback />}>
                  <ResourceHistoryCharts
                    data={resourceHistory}
                    loading={resourceLoading}
                    period={resourcePeriod}
                    onPeriodChange={setResourcePeriod}
                  />
                </Suspense>
              </>
            )}
            {resourceScope === 'panel' && (
              <Suspense fallback={<ChartFallback />}>
                <PanelResourceHistoryCharts
                  period={panelResourcePeriod}
                  onPeriodChange={setPanelResourcePeriod}
                />
              </Suspense>
            )}
            {resourceScope === 'host' && (
              <Suspense fallback={<Spinner label="Загрузка метрик сервера..." className="py-16" />}>
                <ServerMonitorPage embedded />
              </Suspense>
            )}
          </TabsContent>
        )}

        {availableTabs.includes('logs') && (
          <TabsContent value="logs" className="space-y-4">
            <Suspense fallback={<Spinner label="Загрузка журналов..." className="py-16" />}>
              <LogsPage embedded />
            </Suspense>
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}
