import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  Clock,
  Gauge,
  Globe,
  Loader2,
  UserRound,
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
import { getTrafficClientSessions } from '@/api/client'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { PercentBar } from '@/components/ui/percent-bar'
import { formatDateTime } from '@/lib/datetime'
import { formatHaBadgeLabel, haBadgeTitle } from '@/lib/haBadgeLabel'
import { COL_VPN_IP } from '@/lib/uiLabels'
import type { ClientAccessPolicy, TrafficChartData, TrafficClientRow, TrafficClientSessions } from '@/types'

const CHART_VPN = 'hsl(187, 72%, 45%)'
const CHART_ANTIZAPRET = 'hsl(38, 92%, 50%)'

const RANGE_LABELS: Record<string, string> = {
  '1h': '1 час',
  '1d': '24 часа',
  '7d': '7 дней',
  '30d': '30 дней',
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
  return formatDateTime(value)
}

function sessionSummaryHint(sessions: TrafficClientSessions | null) {
  if (!sessions || sessions.total_sessions <= 0) return null
  const { total_sessions, unique_sources } = sessions
  if (unique_sources <= 1 && total_sessions > 1) {
    return 'Счётчик учитывает каждый реконнект; похоже, что это одно устройство с повторными подключениями.'
  }
  if (unique_sources > 0 && total_sessions / unique_sources >= 3) {
    const avg = Math.round(total_sessions / unique_sources)
    return `В среднем ~${avg} подключений на адрес — вероятны реконнекты.`
  }
  return null
}

type MetricTileProps = {
  label: string
  value: string
  sub?: string
}

function MetricTile({ label, value, sub }: MetricTileProps) {
  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mono mt-1 text-lg font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  )
}

type SplitBarProps = {
  label: string
  value: number
  total: number
  variant: 'vpn' | 'antizapret'
}

function SplitBar({ label, value, total, variant }: SplitBarProps) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="mono font-medium tabular-nums">{formatBytes(value)}</span>
      </div>
      <PercentBar
        value={value}
        max={total}
        className="h-2"
        barClassName={variant === 'vpn' ? 'fill-[hsl(187,72%,45%)]' : 'fill-[hsl(38,92%,50%)]'}
      />
    </div>
  )
}

export type TrafficClientDetailsProps = {
  row: TrafficClientRow
  chartData: TrafficChartData | null
  chartLoading: boolean
  chartRange: string
  onChartRangeChange: (range: string) => void
  policy: ClientAccessPolicy | null
  policyLoading?: boolean
}

export default function TrafficClientDetails({
  row,
  chartData,
  chartLoading,
  chartRange,
  onChartRangeChange,
  policy,
  policyLoading = false,
}: TrafficClientDetailsProps) {
  const [showInactiveSources, setShowInactiveSources] = useState(false)
  const [sessions, setSessions] = useState<TrafficClientSessions | null>(null)
  const [sessionsLoading, setSessionsLoading] = useState(false)

  const chartIdSuffix = row.common_name.replace(/[^a-zA-Z0-9]/g, '_')

  useEffect(() => {
    setShowInactiveSources(false)
    setSessionsLoading(true)
    void getTrafficClientSessions(row.common_name, 1)
      .then(setSessions)
      .catch(() => setSessions(null))
      .finally(() => setSessionsLoading(false))
  }, [row.common_name])

  const sessionHint = useMemo(() => sessionSummaryHint(sessions), [sessions])

  const activeSources = useMemo(
    () => sessions?.by_source.filter((source) => source.is_active) ?? [],
    [sessions],
  )
  const inactiveSources = useMemo(
    () => sessions?.by_source.filter((source) => !source.is_active) ?? [],
    [sessions],
  )
  const visibleSources = showInactiveSources
    ? [...activeSources, ...inactiveSources]
    : activeSources

  const renderSourceRows = (sources: TrafficClientSessions['by_source']) =>
    sources.map((source) => (
      <TableRow key={source.client_ip} className={!source.is_active ? 'opacity-80' : undefined}>
        <TableCell>
          <div className="font-mono text-xs">{source.display_address || source.client_ip}</div>
          {source.geo_label ? (
            <div className="mt-0.5 text-[11px] text-muted-foreground">{source.geo_label}</div>
          ) : source.location_label || source.isp ? (
            <div className="mt-0.5 text-[11px] text-muted-foreground">
              {[source.location_label, source.isp].filter(Boolean).join(' · ')}
            </div>
          ) : null}
        </TableCell>
        <TableCell className="text-right font-mono text-xs tabular-nums">
          {source.sessions_count}
          {sessions && sessions.total_sessions > 0 && (
            <span className="ml-1 text-muted-foreground">
              ({Math.round((source.sessions_count / sessions.total_sessions) * 100)}%)
            </span>
          )}
        </TableCell>
        <TableCell className="text-right font-mono text-xs">{formatBytes(source.total_bytes)}</TableCell>
        <TableCell className="font-mono text-xs">{source.virtual_addresses.join(', ') || '—'}</TableCell>
        <TableCell className="text-xs text-muted-foreground">{formatLastSeen(source.last_seen_at)}</TableCell>
        <TableCell>
          <Badge variant={source.is_active ? 'success' : 'secondary'} className="text-[10px]">
            {source.is_active ? 'Сейчас' : 'Был'}
          </Badge>
        </TableCell>
      </TableRow>
    ))

  const chartPoints =
    chartData?.labels?.map((label, i) => ({
      label,
      vpn: chartData.vpn_bytes?.[i] ?? 0,
      antizapret: chartData.antizapret_bytes?.[i] ?? 0,
      total: (chartData.vpn_bytes?.[i] ?? 0) + (chartData.antizapret_bytes?.[i] ?? 0),
    })) ?? []

  const limitPercent =
    policy?.traffic_limit_bytes && policy.traffic_limit_bytes > 0
      ? Math.min(((policy.traffic_consumed_bytes ?? 0) / policy.traffic_limit_bytes) * 100, 100)
      : null

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <p className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <UserRound size={16} />
          Мониторинг клиента
        </p>
        <Badge variant={getProtocolVariant(row.protocol_type)}>{getProtocolLabel(row.protocol_type)}</Badge>
        <Badge variant={row.is_active ? 'success' : 'secondary'}>
          {row.is_active ? 'Онлайн' : 'Офлайн'}
        </Badge>
        {policy?.traffic_limit_exceeded && (
          <Badge variant="destructive" className="gap-1">
            <Gauge size={12} />
            Лимит превышен
          </Badge>
        )}
        {row.ha && (
          <Badge variant="outline" className="gap-1" title={haBadgeTitle(row.ha)}>
            {formatHaBadgeLabel(row.ha)}
          </Badge>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile
          label="Всего"
          value={formatBytes(row.total_bytes)}
          sub={`RX ${formatBytes(row.total_received)} · TX ${formatBytes(row.total_sent)}`}
        />
        <MetricTile label="За 1 день" value={formatBytes(row.traffic_1d)} />
        <MetricTile label="За 7 дней" value={formatBytes(row.traffic_7d)} />
        <MetricTile label="За 30 дней" value={formatBytes(row.traffic_30d)} />
      </div>

      {row.ha_aggregated && row.ha_node_breakdown && row.ha_node_breakdown.length > 0 && (
        <div className="space-y-3 rounded-lg border bg-background p-4">
          <p className="flex items-center gap-2 text-sm font-medium">
            <BarChart3 size={16} />
            По узлам HA-группы
          </p>
          <p className="text-xs text-muted-foreground">
            Итоговые цифры выше — сумма по всем узлам группы.
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Узел</TableHead>
                <TableHead className="text-right">Всего</TableHead>
                <TableHead className="text-right">За 7 дней</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {row.ha_node_breakdown.map((node) => (
                <TableRow key={node.node_id}>
                  <TableCell className="text-sm">{node.node_name}</TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums">
                    {formatBytes(node.total_bytes)}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums">
                    {formatBytes(node.traffic_7d)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={node.is_active ? 'success' : 'secondary'} className="text-[10px]">
                      {node.is_active ? 'Онлайн' : 'Офлайн'}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-3 rounded-lg border bg-background p-4">
          <p className="text-sm font-medium">Разбивка VPN / AntiZapret</p>
          <SplitBar label="VPN" value={row.total_bytes_vpn} total={row.total_bytes} variant="vpn" />
          <SplitBar
            label="AntiZapret"
            value={row.total_bytes_antizapret}
            total={row.total_bytes}
            variant="antizapret"
          />
          <div className="grid grid-cols-1 gap-3 pt-1 text-xs text-muted-foreground sm:grid-cols-2">
            <span>
              Подключений:{' '}
              <strong className="text-foreground">
                {sessions?.total_sessions ?? row.total_sessions}
              </strong>
              {sessions && sessions.unique_sources > 0 && (
                <>
                  {' '}
                  · активных адресов:{' '}
                  <strong className="text-foreground">{activeSources.length}</strong>
                  {inactiveSources.length > 0 && <> из {sessions.unique_sources}</>}
                </>
              )}
            </span>
            <span className="inline-flex items-center gap-1">
              <Clock size={12} />
              Последний раз: <strong className="text-foreground">{formatLastSeen(row.last_seen_at)}</strong>
            </span>
            {row.first_seen_at && (
              <span className="col-span-2">
                Первое появление: <strong className="text-foreground">{formatLastSeen(row.first_seen_at)}</strong>
              </span>
            )}
            {sessionHint && (
              <span className="col-span-2 text-[11px] text-amber-600 dark:text-amber-400">{sessionHint}</span>
            )}
          </div>
        </div>

        <div className="space-y-3 rounded-lg border bg-background p-4">
          <p className="flex items-center gap-2 text-sm font-medium">
            <Gauge size={16} />
            Лимит трафика
          </p>
          {policyLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 size={14} className="animate-spin" />
              Загрузка политики...
            </div>
          ) : policy?.traffic_limit_human ? (
            <>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">
                  {policy.traffic_consumed_human || '0 B'} / {policy.traffic_limit_human}
                  {policy.traffic_limit_period_label ? ` (${policy.traffic_limit_period_label})` : ''}
                </span>
                {policy.traffic_bytes_left_human && (
                  <span className="mono tabular-nums">осталось {policy.traffic_bytes_left_human}</span>
                )}
              </div>
              {limitPercent != null && (
                <PercentBar
                  value={limitPercent}
                  className="h-2"
                  barClassName={policy.traffic_limit_exceeded ? 'fill-destructive' : 'fill-primary'}
                />
              )}
              {policy.traffic_limit_unblock_label && (
                <p className="text-xs text-muted-foreground">Разблокировка: {policy.traffic_limit_unblock_label}</p>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Лимит не задан
              {policy?.traffic_consumed_human ? ` · использовано ${policy.traffic_consumed_human}` : ''}
            </p>
          )}
          {policy?.is_blocked && (
            <Badge variant="destructive">Заблокирован ({policy.block_mode})</Badge>
          )}
        </div>
      </div>

      <div className="space-y-3 rounded-lg border bg-background p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-sm font-medium">
            <Globe size={16} />
            Подключения по адресам
          </p>
          {sessions && sessions.unique_virtual_addresses > 0 && (
            <span className="text-xs text-muted-foreground">
              VPN-адресов: {sessions.unique_virtual_addresses}
            </span>
          )}
        </div>
        {sessionsLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 size={14} className="animate-spin" />
            Анализ сессий...
          </div>
        ) : !sessions || sessions.by_source.length === 0 ? (
          <p className="text-sm text-muted-foreground">Нет сохранённых сессий для разбивки по адресам</p>
        ) : visibleSources.length === 0 ? (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Сейчас нет активных подключений</p>
            {inactiveSources.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                onClick={() => setShowInactiveSources(true)}
              >
                Показать историю ({inactiveSources.length})
              </Button>
            )}
          </div>
        ) : (
          <>
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Адрес клиента</TableHead>
                    <TableHead className="text-right">Подключений</TableHead>
                    <TableHead className="text-right">Трафик</TableHead>
                    <TableHead>{COL_VPN_IP}</TableHead>
                    <TableHead>Последний раз</TableHead>
                    <TableHead>Статус</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>{renderSourceRows(visibleSources)}</TableBody>
              </Table>
            </div>
            {inactiveSources.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 px-2 text-xs"
                onClick={() => setShowInactiveSources((v) => !v)}
              >
                {showInactiveSources
                  ? 'Скрыть историю'
                  : `Показать историю (${inactiveSources.length})`}
              </Button>
            )}
          </>
        )}
      </div>

      <div className="rounded-lg border bg-background">
        <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="flex items-center gap-2 text-sm font-medium">
              <Activity size={16} />
              График трафика клиента
            </p>
            <p className="text-xs text-muted-foreground">
              Дельта байт · {RANGE_LABELS[chartRange] ?? chartRange}
            </p>
          </div>
          <Select value={chartRange} onValueChange={onChartRangeChange}>
            <SelectTrigger className="h-9 w-full text-xs sm:w-[140px]">
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
        <div className="p-4">
          {chartLoading ? (
            <Spinner label="Загрузка графика..." className="py-10" />
          ) : chartPoints.length > 0 ? (
            <ChartResponsive height={280}>
              {({ width, height }) => (
                <AreaChart width={width} height={height} data={chartPoints} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id={`focusTrafficVpn_${chartIdSuffix}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={CHART_VPN} stopOpacity={0.35} />
                      <stop offset="95%" stopColor={CHART_VPN} stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id={`focusTrafficAz_${chartIdSuffix}`} x1="0" y1="0" x2="0" y2="1">
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
                  />
                  <Legend formatter={(value) => (value === 'vpn' ? 'VPN' : 'AntiZapret')} />
                  <Area
                    type="monotone"
                    dataKey="vpn"
                    stackId="1"
                    stroke={CHART_VPN}
                    fill={`url(#focusTrafficVpn_${chartIdSuffix})`}
                    strokeWidth={2}
                    name="vpn"
                  />
                  <Area
                    type="monotone"
                    dataKey="antizapret"
                    stackId="1"
                    stroke={CHART_ANTIZAPRET}
                    fill={`url(#focusTrafficAz_${chartIdSuffix})`}
                    strokeWidth={2}
                    name="antizapret"
                  />
                </AreaChart>
              )}
            </ChartResponsive>
          ) : (
            <EmptyState
              icon={BarChart3}
              title="Нет данных за период"
              description="Расширьте диапазон или дождитесь накопления статистики"
              className="py-8"
            />
          )}
        </div>
      </div>
    </div>
  )
}
