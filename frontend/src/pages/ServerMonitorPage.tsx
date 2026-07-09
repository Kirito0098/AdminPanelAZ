import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity,
  ArrowDownToLine,
  ArrowUpFromLine,
  Clock,
  Cpu,
  Gauge,
  HardDrive,
  Loader2,
  MemoryStick,
  Network,
  RefreshCw,
  Server,
  Wifi,
  WifiOff,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ChartResponsive } from '@/components/monitoring/ChartResponsive'
import ResourceHistoryCharts from '@/components/monitoring/ResourceHistoryCharts'
import { Navigate } from 'react-router-dom'
import { ApiError, getBandwidthChart, getResourceHistory, getServerInterfaces, getServerMetrics } from '@/api/client'
import { NodeBadge } from '@/components/NodeSelector'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { PercentBar } from '@/components/ui/percent-bar'
import { formatDateTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { BandwidthChart, ResourceHistory, ServerMetrics } from '@/types'

import { apiBase as API_BASE } from '@/lib/panelBase'

const CHART_RX = 'hsl(187, 72%, 45%)'
const CHART_TX = 'hsl(38, 92%, 50%)'

const RANGE_LABELS: Record<'1d' | '7d' | '30d', string> = {
  '1d': '1 день',
  '7d': '7 дней',
  '30d': '30 дней',
}

const GROUP_LABELS: Record<string, string> = {
  main: 'Основной интернет',
  vpn: 'VPN',
  antizapret: 'AntiZapret',
  openvpn: 'OpenVPN',
  wireguard: 'WireGuard / AWG',
}

function interfaceTransport(name: string): 'UDP' | 'TCP' | null {
  const lowered = name.toLowerCase()
  if (lowered.endsWith('-udp')) return 'UDP'
  if (lowered.endsWith('-tcp')) return 'TCP'
  return null
}

function interfaceScope(name: string): 'VPN' | 'AntiZapret' | null {
  const lowered = name.toLowerCase()
  if (lowered.includes('antizapret')) return 'AntiZapret'
  if (/(^|[-_])vpn([-_]|$)|wg|wireguard|awg|amnezia/.test(lowered)) return 'VPN'
  return null
}

function inferInterfaceProtocol(
  name: string,
  groups: Record<string, string[]> | undefined,
): 'openvpn' | 'wireguard' | null {
  const inOpenVpn = groups?.openvpn?.includes(name) ?? false
  const inWireguard = groups?.wireguard?.includes(name) ?? false
  if (inOpenVpn && !inWireguard) return 'openvpn'
  if (inWireguard && !inOpenVpn) return 'wireguard'
  if (inOpenVpn && inWireguard) {
    return interfaceTransport(name) ? 'openvpn' : 'wireguard'
  }

  const transport = interfaceTransport(name)
  if (transport) return 'openvpn'

  const lowered = name.toLowerCase()
  if (lowered === 'vpn' || lowered === 'antizapret') return 'wireguard'
  if (lowered.includes('antizapret') || lowered.includes('vpn')) return 'wireguard'
  return null
}

function formatInterfaceLabel(
  name: string,
  primaryInterface?: string | null,
  groups?: Record<string, string[]>,
) {
  if (primaryInterface && name === primaryInterface) {
    return `${name} · основной интернет`
  }

  const scope = interfaceScope(name)
  const protocol = inferInterfaceProtocol(name, groups)
  const transport = interfaceTransport(name)

  if (scope && protocol === 'openvpn') {
    const proto = transport ? `OpenVPN (${transport})` : 'OpenVPN'
    return `${scope} · ${proto} (${name})`
  }
  if (scope && protocol === 'wireguard') {
    return `${scope} · WireGuard / AWG (${name})`
  }
  if (protocol === 'openvpn') {
    const proto = transport ? `OpenVPN (${transport})` : 'OpenVPN'
    return `${proto} (${name})`
  }
  if (protocol === 'wireguard') {
    return `WireGuard / AWG (${name})`
  }
  return name
}

function getUsageBarColor(percent: number) {
  if (percent >= 80) return 'fill-destructive'
  if (percent >= 60) return 'fill-amber-500'
  return 'fill-emerald-500'
}

function getUsageTextColor(percent: number) {
  if (percent >= 80) return 'text-destructive'
  if (percent >= 60) return 'text-amber-500'
  return 'text-emerald-500'
}

function formatGb(bytes: number) {
  return `${(bytes / 1e9).toFixed(1)} GB`
}

function getInterfaceGroups(
  iface: string,
  groups: Record<string, string[]> | undefined,
): string[] {
  if (!groups) return []
  return Object.entries(groups)
    .filter(([, list]) => list.includes(iface))
    .map(([key]) => GROUP_LABELS[key] ?? key)
}

type ResourceGaugeProps = {
  label: string
  value: number
  icon: typeof Cpu
  sub?: string
  unit?: string
}

function ResourceGauge({ label, value, icon: Icon, sub, unit = '%' }: ResourceGaugeProps) {
  const clamped = Math.min(Math.max(value, 0), 100)
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="rounded-md bg-muted p-2 text-muted-foreground">
              <Icon size={16} />
            </div>
            <div>
              <p className="text-sm font-medium">{label}</p>
              {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
            </div>
          </div>
          <span className={cn('mono text-2xl font-bold tabular-nums', getUsageTextColor(clamped))}>
            {Number.isFinite(value) ? `${Math.round(value)}${unit}` : '—'}
          </span>
        </div>
        <PercentBar
          value={clamped}
          className="h-2 transition-all duration-500"
          barClassName={getUsageBarColor(clamped)}
        />
      </CardContent>
    </Card>
  )
}

type LiveMetricProps = {
  label: string
  value: string
  icon: typeof Network
  direction: 'rx' | 'tx'
}

function LiveMetricCard({ label, value, icon: Icon, direction }: LiveMetricProps) {
  const accent = direction === 'rx' ? 'text-primary' : 'text-amber-500'
  const DirectionIcon = direction === 'rx' ? ArrowDownToLine : ArrowUpFromLine
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
          <div className={cn('rounded-md bg-muted p-2', accent)}>
            <Icon size={16} />
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <DirectionIcon size={16} className={cn('shrink-0', accent)} />
          <span className="mono text-2xl font-bold tracking-tight tabular-nums">{value}</span>
        </div>
      </CardContent>
    </Card>
  )
}

export default function ServerMonitorPage() {
  const { user } = useAuth()
  const { activeNode } = useNode()
  const { error: notifyError, success } = useNotifications()
  const { startGlobal, doneGlobal, withInline } = useProgress()
  const [metrics, setMetrics] = useState<ServerMetrics | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [liveCpu, setLiveCpu] = useState<number | null>(null)
  const [liveRam, setLiveRam] = useState<number | null>(null)
  const [liveBw, setLiveBw] = useState<{ rx: number; tx: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [bwLoading, setBwLoading] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const [iface, setIface] = useState('')
  const [ifaces, setIfaces] = useState<string[]>([])
  const [primaryInterface, setPrimaryInterface] = useState<string | null>(null)
  const [interfaceGroups, setInterfaceGroups] = useState<Record<string, string[]>>({})
  const [range, setRange] = useState<'1d' | '7d' | '30d'>('1d')
  const [resourceHistory, setResourceHistory] = useState<ResourceHistory | null>(null)
  const [resourceLoading, setResourceLoading] = useState(false)
  const [resourcePeriod, setResourcePeriod] = useState<'1d' | '7d' | '30d'>('1d')
  const [bwChart, setBwChart] = useState<BandwidthChart | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const loadMetrics = useCallback(async () => {
    try {
      const [m, ifData] = await Promise.all([getServerMetrics(), getServerInterfaces()])
      setMetrics(m)
      setLoadError(null)
      const list = ifData.interfaces || []
      setIfaces(list)
      setInterfaceGroups(ifData.groups || {})
      setPrimaryInterface(ifData.primary_interface ?? null)
      setIface((current) => {
        const preferred = ifData.primary_interface
        if (preferred && list.includes(preferred)) return preferred
        if (list.length && (!current || !list.includes(current))) return list[0]
        return current || list[0] || ''
      })
      return m
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Ошибка загрузки метрик'
      setLoadError(message)
      notifyError(message)
      return null
    }
  }, [notifyError])

  const loadBandwidth = useCallback(
    async (targetIface: string, targetRange: '1d' | '7d' | '30d') => {
      if (!targetIface) return
      setBwLoading(true)
      try {
        setBwChart(await getBandwidthChart(targetIface, targetRange))
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка vnStat')
      } finally {
        setBwLoading(false)
      }
    },
    [notifyError],
  )

  const loadResourceHistory = useCallback(
    async (period: '1d' | '7d' | '30d') => {
      setResourceLoading(true)
      try {
        setResourceHistory(await getResourceHistory(period))
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки истории ресурсов')
      } finally {
        setResourceLoading(false)
      }
    },
    [notifyError],
  )

  useEffect(() => {
    if (user?.role !== 'admin') return
    startGlobal()
    loadMetrics()
      .finally(() => {
        setLoading(false)
        doneGlobal()
      })
  }, [user?.role, loadMetrics, activeNode?.id, startGlobal, doneGlobal])

  useEffect(() => {
    if (user?.role !== 'admin' || !iface) return
    loadBandwidth(iface, range)
  }, [user?.role, iface, range, loadBandwidth, activeNode?.id])

  useEffect(() => {
    if (user?.role !== 'admin') return
    loadResourceHistory(resourcePeriod)
  }, [user?.role, loadResourceHistory, resourcePeriod, activeNode?.id])

  useEffect(() => {
    if (user?.role !== 'admin' || !iface) return
    const token = localStorage.getItem('token')
    if (!token) return

    setWsConnected(false)
    const wsUrl = `${API_BASE.replace('/api', '')}/api/server-monitor/ws?token=${token}&iface=${encodeURIComponent(iface)}`.replace(
      'http',
      'ws',
    )
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => setWsConnected(true)
    ws.onclose = () => setWsConnected(false)
    ws.onerror = () => setWsConnected(false)
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        setLiveCpu(data.cpu_percent)
        setLiveRam(data.memory_percent)
        if (data.bandwidth) {
          setLiveBw({ rx: data.bandwidth.rx_mbps_latest, tx: data.bandwidth.tx_mbps_latest })
        }
      } catch {
        /* ignore */
      }
    }

    return () => ws.close()
  }, [user?.role, iface, activeNode?.id])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await withInline(async () => {
        await loadMetrics()
        await loadBandwidth(iface, range)
        await loadResourceHistory(resourcePeriod)
      }, 'Обновление метрик сервера...')
      success('Метрики сервера обновлены')
    } finally {
      setRefreshing(false)
    }
  }

  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  if (loading) {
    return <Spinner label="Загрузка метрик сервера..." className="py-16" />
  }

  const nodeOffline = activeNode?.status === 'offline'
  const nodeUnknown = activeNode?.status === 'unknown'
  const metricsUnavailable = !!loadError || (!metrics && !liveCpu && !liveRam)

  const cpu = liveCpu ?? metrics?.cpu_percent ?? 0
  const ram = liveRam ?? metrics?.memory_percent ?? 0
  const disk = metrics?.disk_percent ?? 0
  const ramSub = metrics
    ? `${formatGb(metrics.memory_used)} / ${formatGb(metrics.memory_total)}`
    : undefined

  const chartData =
    bwChart?.labels?.map((label, i) => ({
      label,
      rx: bwChart.rx_mbps[i] ?? 0,
      tx: bwChart.tx_mbps[i] ?? 0,
    })) ?? []

  const interfaceList = ifaces.length ? ifaces : iface ? [iface] : []
  const selectedGroups = getInterfaceGroups(iface, interfaceGroups)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Cpu size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold tracking-tight">Сервер</h2>
              <NodeBadge name={activeNode?.name ?? metrics?.node_name} status={activeNode?.status} />
              {wsConnected ? (
                <Badge variant="success" className="gap-1 text-[10px]">
                  <Wifi size={10} />
                  Live
                </Badge>
              ) : (
                <Badge variant="secondary" className="gap-1 text-[10px]">
                  <WifiOff size={10} />
                  WS
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              CPU, RAM, диск и трафик vnStat · WebSocket каждые 2 с
              {metrics?.hostname ? ` · ${metrics.hostname}` : ''}
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={refreshing}>
          <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
          Обновить
        </Button>
      </div>

      <SettingsAlert variant="info" title="Данные активного узла">
        Метрики собираются с <strong>{activeNode?.name ?? metrics?.node_name ?? 'активного узла'}</strong>
        {activeNode?.is_local ? ' (локальный controller)' : ' (удалённый node agent)'}.
        Переключите узел в шапке или на странице «Узлы», чтобы смотреть другой сервер.
      </SettingsAlert>

      {nodeOffline && (
        <SettingsAlert variant="warning" title="Узел офлайн">
          Активный узел недоступен. Метрики могут быть устаревшими или отсутствовать. Проверьте связь с node
          agent и повторите обновление.
        </SettingsAlert>
      )}

      {nodeUnknown && !nodeOffline && (
        <SettingsAlert variant="warning" title="Статус узла неизвестен">
          Связь с узлом не подтверждена. Запустите проверку здоровья на странице «Узлы».
        </SettingsAlert>
      )}

      <InlineProgressBar
        active={refreshing || bwLoading || resourceLoading}
        label={
          refreshing
            ? 'Обновление метрик...'
            : bwLoading
              ? 'Загрузка графика vnStat...'
              : resourceLoading
                ? 'Загрузка истории ресурсов...'
                : undefined
        }
      />

      {metricsUnavailable ? (
        <Card>
          <CardContent>
            <EmptyState
              icon={Server}
              title="Метрики недоступны"
              description={
                loadError ??
                'Не удалось получить данные с активного узла. Убедитесь, что node agent запущен и узел в сети.'
              }
              action={
                <Button onClick={handleRefresh} disabled={refreshing}>
                  {refreshing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                  Повторить
                </Button>
              }
              className="py-8"
            />
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <ResourceGauge label="CPU" value={cpu} icon={Cpu} sub="Загрузка процессора" />
            <ResourceGauge label="RAM" value={ram} icon={MemoryStick} sub={ramSub} />
            <ResourceGauge label="Диск" value={disk} icon={HardDrive} sub="Использование корневого раздела" />
          </div>

          <ResourceHistoryCharts
            data={resourceHistory}
            loading={resourceLoading}
            period={resourcePeriod}
            onPeriodChange={setResourcePeriod}
            showLatestSummary={false}
            title="История CPU / RAM / Диск"
            description={`Снимки каждые ~60 с · ${RANGE_LABELS[resourcePeriod]}${
              resourceHistory && resourceHistory.sample_count > 0
                ? ` · ${resourceHistory.sample_count} точек`
                : ''
            }`}
          />

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <LiveMetricCard
              label="RX (live)"
              value={liveBw ? `${liveBw.rx} Mbps` : '—'}
              icon={Network}
              direction="rx"
            />
            <LiveMetricCard
              label="TX (live)"
              value={liveBw ? `${liveBw.tx} Mbps` : '—'}
              icon={Activity}
              direction="tx"
            />
            <Card>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Uptime</span>
                  <div className="rounded-md bg-muted p-2 text-muted-foreground">
                    <Clock size={16} />
                  </div>
                </div>
                <div className="mono mt-2 text-2xl font-bold tracking-tight">{metrics?.uptime || '—'}</div>
                {metrics?.timestamp && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Снимок: {formatDateTime(metrics.timestamp)}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Activity size={18} />
                  Трафик (vnStat)
                </CardTitle>
                <CardDescription>
                  История пропускной способности · {RANGE_LABELS[range]}
                  {selectedGroups.length > 0 && ` · ${selectedGroups.join(', ')}`}
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Select value={iface} onValueChange={setIface}>
                  <SelectTrigger className="h-9 w-full min-w-[220px] max-w-[320px] text-xs sm:w-[280px]">
                    <SelectValue placeholder="Интерфейс" />
                  </SelectTrigger>
                  <SelectContent>
                    {interfaceList.map((i) => (
                      <SelectItem key={i} value={i}>
                        {formatInterfaceLabel(i, primaryInterface, interfaceGroups)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {(['1d', '7d', '30d'] as const).map((r) => (
                  <Button key={r} size="sm" variant={range === r ? 'default' : 'outline'} onClick={() => setRange(r)}>
                    {RANGE_LABELS[r]}
                  </Button>
                ))}
              </div>
            </CardHeader>
            <CardContent>
              {bwLoading ? (
                <Spinner label="Загрузка графика..." className="py-12" />
              ) : bwChart?.error ? (
                <EmptyState
                  icon={Network}
                  title="vnStat недоступен"
                  description={
                    bwChart.error.includes('vnstat не установлен')
                      ? `${activeNode?.is_local ? 'На этом сервере' : `На узле «${activeNode?.name ?? metrics?.node_name ?? 'удалённый'}»`} не установлен vnStat. Подключитесь по SSH к VPN-узлу и выполните: apt install -y vnstat && sudo ./scripts/setup-vnstat.sh`
                      : bwChart.error
                  }
                  className="py-8"
                />
              ) : chartData.length > 0 ? (
                <ChartResponsive height={300}>
                  {({ width, height }) => (
                <AreaChart width={width} height={height} data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="bwRx" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={CHART_RX} stopOpacity={0.35} />
                        <stop offset="95%" stopColor={CHART_RX} stopOpacity={0.02} />
                      </linearGradient>
                      <linearGradient id="bwTx" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={CHART_TX} stopOpacity={0.35} />
                        <stop offset="95%" stopColor={CHART_TX} stopOpacity={0.02} />
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
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      unit=" Mbps"
                      width={56}
                    />
                    <Tooltip
                      cursor={{ stroke: 'hsl(var(--muted-foreground))', strokeWidth: 1, strokeDasharray: '4 4' }}
                      formatter={(value: number, name: string) => [
                        `${Number(value).toFixed(2)} Mbps`,
                        name === 'rx' ? 'Приём (RX)' : 'Передача (TX)',
                      ]}
                      labelFormatter={(label) => `Период: ${label}`}
                    />
                    <Legend formatter={(value) => (value === 'rx' ? 'Приём (RX)' : 'Передача (TX)')} />
                    <Area
                      type="monotone"
                      dataKey="rx"
                      name="rx"
                      stroke={CHART_RX}
                      fill="url(#bwRx)"
                      strokeWidth={2}
                      activeDot={{ r: 5, strokeWidth: 2, stroke: 'hsl(var(--background))' }}
                    />
                    <Area
                      type="monotone"
                      dataKey="tx"
                      name="tx"
                      stroke={CHART_TX}
                      fill="url(#bwTx)"
                      strokeWidth={2}
                      activeDot={{ r: 5, strokeWidth: 2, stroke: 'hsl(var(--background))' }}
                    />
                  </AreaChart>
                  )}
                </ChartResponsive>
              ) : (
                <EmptyState
                  icon={Network}
                  title="Нет данных vnStat"
                  description="Для выбранного интерфейса нет истории трафика. Проверьте, что vnStat установлен и интерфейс активен."
                  className="py-8"
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Gauge size={18} />
                Load average
              </CardTitle>
              <CardDescription>Средняя загрузка системы за 1, 5 и 15 минут</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  { key: 'load_1m', label: '1 мин' },
                  { key: 'load_5m', label: '5 мин' },
                  { key: 'load_15m', label: '15 мин' },
                ].map(({ key, label }) => {
                  const value = metrics?.load_average?.[key]
                  return (
                    <div key={key} className="rounded-lg border bg-muted/30 px-4 py-3 text-center">
                      <p className="text-xs text-muted-foreground">{label}</p>
                      <p className="mono mt-1 text-xl font-semibold tabular-nums">
                        {value !== undefined ? value.toFixed(2) : '—'}
                      </p>
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
