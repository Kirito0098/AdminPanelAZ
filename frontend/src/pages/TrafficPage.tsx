import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  ArrowDownToLine,
  ArrowUpFromLine,
  BarChart3,
  Clock,
  Database,
  HardDrive,
  Loader2,
  Network,
  RotateCcw,
  Search,
  TrendingUp,
  Users,
  Trash2,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  ApiError,
  cleanupTrafficStatusLogs,
  deleteDeletedClientTraffic,
  getDeletedClientTraffic,
  getTrafficChart,
  getTrafficCleanupSchedule,
  getTrafficActiveClients,
  getTrafficOverview,
  resetTraffic,
  setTrafficCleanupSchedule,
} from '@/api/client'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
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
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { cn } from '@/lib/utils'
import type { TrafficChartData, TrafficClientRow, TrafficOverview } from '@/types'

const REFRESH_INTERVAL = 60

const CHART_VPN = 'hsl(187, 72%, 45%)'
const CHART_ANTIZAPRET = 'hsl(38, 92%, 50%)'
const BAR_COLORS = [
  'hsl(187, 72%, 45%)',
  'hsl(142, 71%, 45%)',
  'hsl(38, 92%, 50%)',
  'hsl(217, 33%, 55%)',
  'hsl(280, 45%, 55%)',
  'hsl(0, 72%, 55%)',
  'hsl(160, 50%, 45%)',
  'hsl(30, 80%, 50%)',
]

const RANGE_LABELS: Record<string, string> = {
  '1h': '1 час',
  '1d': '24 часа',
  '7d': '7 дней',
  '30d': '30 дней',
}

type SortKey = 'total_bytes' | 'traffic_7d' | 'traffic_1d' | 'total_received' | 'total_sent' | 'common_name'

const SORT_LABELS: Record<SortKey, string> = {
  total_bytes: 'Общий объём',
  traffic_7d: 'За 7 дней',
  traffic_1d: 'За 1 день',
  total_received: 'RX',
  total_sent: 'TX',
  common_name: 'Имя клиента',
}

function getProtocolLabel(protocol: string) {
  const p = protocol.toLowerCase()
  if (p === 'wireguard') return 'WireGuard'
  if (p === 'openvpn') return 'OpenVPN'
  return protocol
}

function getProtocolVariant(protocol: string): 'default' | 'secondary' | 'outline' {
  const p = protocol.toLowerCase()
  if (p === 'openvpn') return 'default'
  if (p === 'wireguard') return 'secondary'
  return 'outline'
}

function formatLastSeen(value?: string | null) {
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

type TrafficShareBarProps = {
  value: number
  max: number
}

function TrafficShareBar({ value, max }: TrafficShareBarProps) {
  const percent = max > 0 ? Math.min((value / max) * 100, 100) : 0
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 min-w-[4rem] flex-1 overflow-hidden rounded-full bg-secondary">
        <div
          className="h-full rounded-full bg-primary transition-all duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="mono w-10 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground">
        {percent.toFixed(0)}%
      </span>
    </div>
  )
}

type TrafficClientCardProps = {
  row: TrafficClientRow
  maxBytes: number
  selected: boolean
  onSelect: () => void
}

function TrafficClientCard({ row, maxBytes, selected, onSelect }: TrafficClientCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'w-full rounded-lg border p-4 text-left transition-colors hover:bg-muted/40',
        selected && 'border-primary/50 bg-primary/5',
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium">{row.common_name}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{formatLastSeen(row.last_seen_at)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant={getProtocolVariant(row.protocol_type)} className="text-[10px]">
            {getProtocolLabel(row.protocol_type)}
          </Badge>
          <Badge variant={row.is_active ? 'success' : 'secondary'} className="text-[10px]">
            {row.is_active ? 'Онлайн' : 'Офлайн'}
          </Badge>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-muted-foreground">RX / TX</p>
          <p className="mono font-medium">
            {formatBytes(row.total_received)} / {formatBytes(row.total_sent)}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Всего</p>
          <p className="mono font-medium">{formatBytes(row.total_bytes)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">1д / 7д</p>
          <p className="mono font-medium">
            {formatBytes(row.traffic_1d)} / {formatBytes(row.traffic_7d)}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">30д</p>
          <p className="mono font-medium">{formatBytes(row.traffic_30d)}</p>
        </div>
      </div>
      <div className="mt-3">
        <TrafficShareBar value={row.total_bytes} max={maxBytes} />
      </div>
    </button>
  )
}

export default function TrafficPage() {
  const { activeNode } = useNode()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal, inline, withInline } = useProgress()
  const [data, setData] = useState<TrafficOverview | null>(null)
  const [chartData, setChartData] = useState<TrafficChartData | null>(null)
  const [selectedClient, setSelectedClient] = useState<string>('')
  const [chartRange, setChartRange] = useState('7d')
  const [loading, setLoading] = useState(true)
  const [liveLoading, setLiveLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [chartLoading, setChartLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('total_bytes')
  const [resetting, setResetting] = useState(false)
  const [resetScope, setResetScope] = useState<'all' | 'openvpn' | 'wireguard'>('all')
  const [deletedRows, setDeletedRows] = useState<
    Array<{
      common_name: string
      protocol_type: string
      total_bytes: number
      last_seen_at?: string | null
    }>
  >([])
  const [deletedSummary, setDeletedSummary] = useState<{ users_count: number; total_bytes: number } | null>(null)
  const [cleanupPeriod, setCleanupPeriod] = useState('none')
  const [maintenanceLoading, setMaintenanceLoading] = useState(false)

  const load = useCallback(
    async (initial = false, manual = false) => {
      if (initial) {
        setLoading(true)
        startGlobal()
      }
      if (manual) setRefreshing(true)
      try {
        const overview = await getTrafficOverview(false)
        setData(overview)
        setLoadError(null)
        setSelectedClient((current) => {
          if (current && overview.rows.some((r) => r.common_name === current)) return current
          return overview.rows[0]?.common_name ?? ''
        })
        setCountdown(REFRESH_INTERVAL)

        if (!initial) setLiveLoading(true)
        void getTrafficActiveClients()
          .then(({ active_clients }) => {
            const activeSet = new Set(active_clients)
            setData((prev) => {
              if (!prev) return prev
              return {
                ...prev,
                rows: prev.rows.map((row) => ({
                  ...row,
                  is_active: activeSet.has(row.common_name),
                })),
              }
            })
          })
          .catch(() => {})
          .finally(() => {
            setLiveLoading(false)
          })
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : 'Ошибка загрузки трафика'
        setLoadError(message)
        notifyError(message)
      } finally {
        setLoading(false)
        setRefreshing(false)
        if (initial) doneGlobal()
      }
    },
    [startGlobal, doneGlobal, notifyError],
  )

  const loadChart = useCallback(async () => {
    if (!selectedClient) return
    setChartLoading(true)
    try {
      setChartData(await getTrafficChart(selectedClient, chartRange))
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки графика')
    } finally {
      setChartLoading(false)
    }
  }, [selectedClient, chartRange, notifyError])

  useEffect(() => {
    load(true)
  }, [load, activeNode?.id])

  const loadDeletedClients = useCallback(async () => {
    if (!isAdmin) return
    try {
      const result = await getDeletedClientTraffic()
      setDeletedRows(result.rows)
      setDeletedSummary(result.summary)
    } catch {
      setDeletedRows([])
      setDeletedSummary(null)
    }
  }, [isAdmin])

  const loadCleanupSchedule = useCallback(async () => {
    if (!isAdmin) return
    try {
      const schedule = await getTrafficCleanupSchedule()
      setCleanupPeriod(schedule.period)
    } catch {
      setCleanupPeriod('none')
    }
  }, [isAdmin])

  useEffect(() => {
    void loadDeletedClients()
    void loadCleanupSchedule()
  }, [loadDeletedClients, loadCleanupSchedule, activeNode?.id])

  useEffect(() => {
    loadChart()
  }, [loadChart])

  useEffect(() => {
    if (!autoRefresh) return
    const tick = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          load()
          return REFRESH_INTERVAL
        }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(tick)
  }, [autoRefresh, load])

  const summary = data?.summary
  const nodeOffline = activeNode?.status === 'offline'
  const nodeUnknown = activeNode?.status === 'unknown'

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const rows = [...(data?.rows ?? [])]
    const filtered = q
      ? rows.filter(
          (r) =>
            r.common_name.toLowerCase().includes(q) ||
            getProtocolLabel(r.protocol_type).toLowerCase().includes(q),
        )
      : rows

    filtered.sort((a, b) => {
      if (sortKey === 'common_name') {
        return a.common_name.localeCompare(b.common_name, 'ru')
      }
      return (b[sortKey] as number) - (a[sortKey] as number)
    })
    return filtered
  }, [data?.rows, search, sortKey])

  const maxBytes = useMemo(
    () => Math.max(...(filteredRows.map((r) => r.total_bytes) ?? [0]), 1),
    [filteredRows],
  )

  const topConsumer = useMemo(() => {
    const rows = data?.rows ?? []
    if (!rows.length) return null
    return [...rows].sort((a, b) => b.traffic_7d - a.traffic_7d)[0]
  }, [data?.rows])

  const topChartData = useMemo(
    () =>
      [...(data?.rows ?? [])]
        .sort((a, b) => b.traffic_7d - a.traffic_7d)
        .slice(0, 8)
        .map((r) => ({ name: r.common_name, traffic: r.traffic_7d })),
    [data?.rows],
  )

  const chartPoints =
    chartData?.labels?.map((label, i) => ({
      label,
      vpn: chartData.vpn_bytes?.[i] ?? 0,
      antizapret: chartData.antizapret_bytes?.[i] ?? 0,
      total: (chartData.vpn_bytes?.[i] ?? 0) + (chartData.antizapret_bytes?.[i] ?? 0),
    })) ?? []

  const handleRefresh = () => load(false, true)

  const handleReset = async () => {
    setResetting(true)
    try {
      await withInline(async () => {
        await resetTraffic(resetScope)
        await load(false, true)
        await loadDeletedClients()
      }, 'Сброс статистики трафика...')
      success(`Статистика сброшена (${resetScope})`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сброса')
    } finally {
      setResetting(false)
    }
  }

  const handleDeleteDeletedClient = async (clientName: string) => {
    setMaintenanceLoading(true)
    try {
      await deleteDeletedClientTraffic(clientName)
      success(`Статистика «${clientName}» удалена`)
      await load(false, true)
      await loadDeletedClients()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления')
    } finally {
      setMaintenanceLoading(false)
    }
  }

  const handleCleanupLogs = async () => {
    setMaintenanceLoading(true)
    try {
      const resp = await cleanupTrafficStatusLogs()
      success(resp.message)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка очистки логов')
    } finally {
      setMaintenanceLoading(false)
    }
  }

  const handleCleanupScheduleChange = async (period: string) => {
    setMaintenanceLoading(true)
    try {
      const resp = await setTrafficCleanupSchedule(period)
      setCleanupPeriod(period)
      success(resp.message)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка расписания')
    } finally {
      setMaintenanceLoading(false)
    }
  }

  if (loading && !data) {
    return <Spinner label="Загрузка статистики трафика..." className="py-16" />
  }

  const hasRows = (data?.rows?.length ?? 0) > 0

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Network size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold tracking-tight">Мониторинг трафика</h2>
              <NodeBadge name={activeNode?.name ?? data?.node_name} status={activeNode?.status} />
              {liveLoading && (
                <Badge variant="secondary" className="gap-1 text-[10px]">
                  <Loader2 size={10} className="animate-spin" />
                  Live-статус
                </Badge>
              )}
              {summary?.db_is_stale && (
                <Badge variant="warning" className="gap-1 text-[10px]">
                  <Database size={10} />
                  БД устарела ({summary.db_age_seconds}с)
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              Накопленная статистика RX/TX по клиентам VPN и AntiZapret
              {data?.timestamp && (
                <> · обновлено {new Date(data.timestamp).toLocaleString('ru-RU')}</>
              )}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <AutoRefreshControl
            enabled={autoRefresh}
            onToggle={() => setAutoRefresh((v) => !v)}
            countdown={countdown}
            intervalSec={REFRESH_INTERVAL}
            refreshing={refreshing}
            onManualRefresh={handleRefresh}
          />
          {isAdmin && (
            <>
              <Select value={resetScope} onValueChange={(v) => setResetScope(v as typeof resetScope)}>
                <SelectTrigger className="h-9 w-[160px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Сброс: всё</SelectItem>
                  <SelectItem value="openvpn">Сброс: OpenVPN</SelectItem>
                  <SelectItem value="wireguard">Сброс: WG/AWG</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm" onClick={handleReset} disabled={resetting}>
                {resetting ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                Сбросить
              </Button>
            </>
          )}
        </div>
      </div>

      <SettingsAlert variant="info" title="Данные активного узла">
        Статистика трафика собирается с <strong>{activeNode?.name ?? data?.node_name ?? 'активного узла'}</strong>
        {activeNode?.is_local ? ' (локальный controller)' : ' (удалённый node agent)'}.
        Коллектор обновляет БД каждые 30 с. Переключите узел в шапке или на странице «Узлы».
      </SettingsAlert>

      {nodeOffline && (
        <SettingsAlert variant="warning" title="Узел офлайн">
          Активный узел недоступен. Статистика может быть устаревшей или не обновляться. Проверьте связь с node
          agent и повторите обновление.
        </SettingsAlert>
      )}

      {nodeUnknown && !nodeOffline && (
        <SettingsAlert variant="warning" title="Статус узла неизвестен">
          Связь с узлом не подтверждена. Данные трафика могут быть неактуальными — запустите проверку здоровья на
          странице «Узлы».
        </SettingsAlert>
      )}

      <InlineProgressBar
        active={inline.active || refreshing}
        label={inline.label || (refreshing ? 'Обновление статистики...' : undefined)}
      />

      {loadError && !hasRows ? (
        <Card>
          <CardContent>
            <EmptyState
              icon={HardDrive}
              title="Статистика недоступна"
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
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard
              label="Клиентов"
              value={String(summary?.users_count ?? 0)}
              icon={Users}
              sub={`активных: ${summary?.active_users_count ?? 0}`}
            />
            <SummaryCard
              label="Получено (RX)"
              value={formatBytes(summary?.total_received ?? 0)}
              icon={ArrowDownToLine}
              accent="text-primary"
            />
            <SummaryCard
              label="Отправлено (TX)"
              value={formatBytes(summary?.total_sent ?? 0)}
              icon={ArrowUpFromLine}
              accent="text-amber-500"
            />
            <SummaryCard
              label="Топ за 7д"
              value={topConsumer ? formatBytes(topConsumer.traffic_7d) : '—'}
              icon={TrendingUp}
              sub={topConsumer ? topConsumer.common_name : 'нет данных'}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Activity size={18} />
                    График трафика
                  </CardTitle>
                  <CardDescription>
                    Дельта байт по времени · {RANGE_LABELS[chartRange] ?? chartRange}
                    {selectedClient && ` · ${selectedClient}`}
                  </CardDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Select value={selectedClient} onValueChange={setSelectedClient}>
                    <SelectTrigger className="h-9 w-[180px] text-xs">
                      <SelectValue placeholder="Клиент" />
                    </SelectTrigger>
                    <SelectContent>
                      {data?.rows.map((r) => (
                        <SelectItem key={`${r.common_name}-${r.protocol_type}`} value={r.common_name}>
                          {r.common_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select value={chartRange} onValueChange={setChartRange}>
                    <SelectTrigger className="h-9 w-[120px] text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1h">1 час</SelectItem>
                      <SelectItem value="1d">24 часа</SelectItem>
                      <SelectItem value="7d">7 дней</SelectItem>
                      <SelectItem value="30d">30 дней</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardHeader>
              <CardContent>
                {chartLoading ? (
                  <Spinner label="Загрузка графика..." className="py-12" />
                ) : chartPoints.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <AreaChart data={chartPoints} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="trafficVpn" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={CHART_VPN} stopOpacity={0.35} />
                          <stop offset="95%" stopColor={CHART_VPN} stopOpacity={0.02} />
                        </linearGradient>
                        <linearGradient id="trafficAz" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={CHART_ANTIZAPRET} stopOpacity={0.35} />
                          <stop offset="95%" stopColor={CHART_ANTIZAPRET} stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
                      <XAxis
                        dataKey="label"
                        tick={{ fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        tickFormatter={(v) => formatBytes(v)}
                        tick={{ fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        width={64}
                      />
                      <Tooltip
                        formatter={(v: number, name: string) => [
                          formatBytes(v),
                          name === 'vpn' ? 'VPN' : 'AntiZapret',
                        ]}
                        labelFormatter={(label) => `Период: ${label}`}
                        contentStyle={{
                          borderRadius: '8px',
                          border: '1px solid hsl(var(--border))',
                          background: 'hsl(var(--popover))',
                          fontSize: '12px',
                        }}
                      />
                      <Legend
                        formatter={(value) => (value === 'vpn' ? 'VPN' : 'AntiZapret')}
                        wrapperStyle={{ fontSize: '12px' }}
                      />
                      <Area
                        type="monotone"
                        dataKey="vpn"
                        stackId="1"
                        stroke={CHART_VPN}
                        fill="url(#trafficVpn)"
                        strokeWidth={2}
                        name="vpn"
                      />
                      <Area
                        type="monotone"
                        dataKey="antizapret"
                        stackId="1"
                        stroke={CHART_ANTIZAPRET}
                        fill="url(#trafficAz)"
                        strokeWidth={2}
                        name="antizapret"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState
                    icon={BarChart3}
                    title="Нет данных за период"
                    description="Выберите другого клиента или расширьте временной диапазон"
                    className="py-8"
                  />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <BarChart3 size={18} />
                  Топ клиентов (7д)
                </CardTitle>
                <CardDescription>Наибольший объём трафика за последние 7 дней</CardDescription>
              </CardHeader>
              <CardContent>
                {topChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={topChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 10 }}
                        tickLine={false}
                        axisLine={false}
                        interval={0}
                        angle={-25}
                        textAnchor="end"
                        height={56}
                      />
                      <YAxis
                        tickFormatter={(v) => formatBytes(v)}
                        tick={{ fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        width={64}
                      />
                      <Tooltip
                        formatter={(v: number) => [formatBytes(v), '7 дней']}
                        contentStyle={{
                          borderRadius: '8px',
                          border: '1px solid hsl(var(--border))',
                          background: 'hsl(var(--popover))',
                          fontSize: '12px',
                        }}
                      />
                      <Bar dataKey="traffic" name="7 дней" radius={[4, 4, 0, 0]}>
                        {topChartData.map((_, i) => (
                          <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState
                    icon={Users}
                    title="Нет клиентов"
                    description="Статистика появится после первого сбора данных коллектором"
                    className="py-8"
                  />
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-base">
                  <HardDrive size={18} />
                  Клиенты
                </CardTitle>
                <CardDescription>
                  {hasRows
                    ? `${filteredRows.length} из ${data?.rows.length ?? 0} клиентов · сортировка: ${SORT_LABELS[sortKey]}`
                    : 'Накопленные RX/TX, окна 1д / 7д / 30д'}
                  {summary?.latest_sample_at && (
                    <> · последний снимок {new Date(summary.latest_sample_at).toLocaleString('ru-RU')}</>
                  )}
                </CardDescription>
              </div>
              <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
                <div className="relative sm:w-56">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Поиск по имени..."
                    className="h-9 pl-9 text-xs"
                  />
                </div>
                <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
                  <SelectTrigger className="h-9 w-full text-xs sm:w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                      <SelectItem key={key} value={key}>
                        {SORT_LABELS[key]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {!hasRows ? (
                <EmptyState
                  icon={HardDrive}
                  title="Нет накопленной статистики"
                  description="Коллектор запускается автоматически каждые 30 с. Данные появятся после первых подключений клиентов."
                  className="py-8"
                />
              ) : filteredRows.length === 0 ? (
                <EmptyState
                  icon={Search}
                  title="Нет совпадений"
                  description="Измените поисковый запрос или сбросьте фильтр"
                  className="py-8"
                />
              ) : (
                <>
                  <div className="space-y-3 lg:hidden">
                    {filteredRows.map((r) => (
                      <TrafficClientCard
                        key={`${r.common_name}-${r.protocol_type}`}
                        row={r}
                        maxBytes={maxBytes}
                        selected={selectedClient === r.common_name}
                        onSelect={() => setSelectedClient(r.common_name)}
                      />
                    ))}
                  </div>

                  <div className="hidden overflow-x-auto rounded-md border lg:block">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Клиент</TableHead>
                          <TableHead>Протокол</TableHead>
                          <TableHead className="text-right">RX</TableHead>
                          <TableHead className="text-right">TX</TableHead>
                          <TableHead className="text-right">Всего</TableHead>
                          <TableHead className="min-w-[8rem]">Доля</TableHead>
                          <TableHead className="text-right">1д</TableHead>
                          <TableHead className="text-right">7д</TableHead>
                          <TableHead className="text-right">30д</TableHead>
                          <TableHead>Последний раз</TableHead>
                          <TableHead>Статус</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredRows.map((r) => (
                          <TableRow
                            key={`${r.common_name}-${r.protocol_type}`}
                            className={cn(
                              'cursor-pointer hover:bg-muted/50',
                              selectedClient === r.common_name && 'bg-primary/5',
                            )}
                            onClick={() => setSelectedClient(r.common_name)}
                          >
                            <TableCell className="font-medium">{r.common_name}</TableCell>
                            <TableCell>
                              <Badge variant={getProtocolVariant(r.protocol_type)} className="text-[10px]">
                                {getProtocolLabel(r.protocol_type)}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs">
                              {formatBytes(r.total_received)}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs">
                              {formatBytes(r.total_sent)}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs font-medium">
                              {formatBytes(r.total_bytes)}
                            </TableCell>
                            <TableCell>
                              <TrafficShareBar value={r.total_bytes} max={maxBytes} />
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs">
                              {formatBytes(r.traffic_1d)}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs">
                              {formatBytes(r.traffic_7d)}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs">
                              {formatBytes(r.traffic_30d)}
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground">
                              <span className="inline-flex items-center gap-1">
                                <Clock size={12} className="shrink-0" />
                                {formatLastSeen(r.last_seen_at)}
                              </span>
                            </TableCell>
                            <TableCell>
                              <Badge variant={r.is_active ? 'success' : 'secondary'} className="text-[10px]">
                                {r.is_active ? 'Онлайн' : 'Офлайн'}
                              </Badge>
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

          {isAdmin && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Обслуживание БД трафика</CardTitle>
                <CardDescription>
                  Удалённые клиенты, очистка OpenVPN-логов (кроме *-status.log)
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex flex-wrap items-end gap-3">
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Расписание очистки .log</Label>
                    <Select
                      value={cleanupPeriod}
                      onValueChange={(v) => void handleCleanupScheduleChange(v)}
                      disabled={maintenanceLoading}
                    >
                      <SelectTrigger className="h-9 w-[180px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">Выключено</SelectItem>
                        <SelectItem value="daily">Ежедневно</SelectItem>
                        <SelectItem value="weekly">Еженедельно</SelectItem>
                        <SelectItem value="monthly">Ежемесячно</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => void handleCleanupLogs()} disabled={maintenanceLoading}>
                    Очистить .log сейчас
                  </Button>
                </div>

                <div>
                  <p className="mb-2 text-sm text-muted-foreground">
                    Клиенты без конфигов: <strong>{deletedSummary?.users_count ?? 0}</strong>, суммарный трафик:{' '}
                    <strong>{formatBytes(deletedSummary?.total_bytes ?? 0)}</strong>
                  </p>
                  {deletedRows.length === 0 ? (
                    <EmptyState
                      icon={Database}
                      title="Нет осиротевшей статистики"
                      description="Все записи соответствуют активным конфигам"
                      className="py-6"
                    />
                  ) : (
                    <div className="overflow-x-auto rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Клиент</TableHead>
                            <TableHead>Протокол</TableHead>
                            <TableHead className="text-right">Всего</TableHead>
                            <TableHead className="w-[100px]" />
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {deletedRows.map((row) => (
                            <TableRow key={`${row.common_name}-${row.protocol_type}`}>
                              <TableCell>{row.common_name}</TableCell>
                              <TableCell>{getProtocolLabel(row.protocol_type)}</TableCell>
                              <TableCell className="text-right font-mono text-xs">{formatBytes(row.total_bytes)}</TableCell>
                              <TableCell>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-destructive"
                                  disabled={maintenanceLoading}
                                  onClick={() => void handleDeleteDeletedClient(row.common_name)}
                                >
                                  <Trash2 size={14} />
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
