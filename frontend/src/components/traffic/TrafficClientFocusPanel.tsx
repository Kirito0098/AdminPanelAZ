import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  BarChart3,
  Clock,
  Gauge,
  Globe,
  Loader2,
  Search,
  UserRound,
  X,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getTrafficClientSessions } from '@/api/client'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
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
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
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
  return new Date(value).toLocaleString('ru-RU')
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
  color: string
}

function SplitBar({ label, value, total, color }: SplitBarProps) {
  const percent = total > 0 ? Math.min((value / total) * 100, 100) : 0
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="mono font-medium tabular-nums">{formatBytes(value)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full transition-all duration-300" style={{ width: `${percent}%`, background: color }} />
      </div>
    </div>
  )
}

export type TrafficClientFocusPanelProps = {
  rows: TrafficClientRow[]
  selectedClient: string
  onSelectClient: (name: string) => void
  focusOnly: boolean
  onFocusOnlyChange: (value: boolean) => void
  chartData: TrafficChartData | null
  chartLoading: boolean
  chartRange: string
  onChartRangeChange: (range: string) => void
  policy: ClientAccessPolicy | null
  policyLoading?: boolean
}

export default function TrafficClientFocusPanel({
  rows,
  selectedClient,
  onSelectClient,
  focusOnly,
  onFocusOnlyChange,
  chartData,
  chartLoading,
  chartRange,
  onChartRangeChange,
  policy,
  policyLoading = false,
}: TrafficClientFocusPanelProps) {
  const [query, setQuery] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [showInactiveSources, setShowInactiveSources] = useState(false)
  const [sessions, setSessions] = useState<TrafficClientSessions | null>(null)
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const selectedRow = useMemo(
    () => rows.find((row) => row.common_name === selectedClient) ?? null,
    [rows, selectedClient],
  )

  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase()
    const sorted = [...rows].sort((a, b) => b.traffic_7d - a.traffic_7d)
    if (!q) return sorted.slice(0, 8)
    return sorted
      .filter(
        (row) =>
          row.common_name.toLowerCase().includes(q) ||
          getProtocolLabel(row.protocol_type).toLowerCase().includes(q),
      )
      .slice(0, 8)
  }, [query, rows])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setPickerOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => {
    if (!selectedClient) {
      setSessions(null)
      setShowInactiveSources(false)
      return
    }
    setSessionsLoading(true)
    void getTrafficClientSessions(selectedClient, 1)
      .then(setSessions)
      .catch(() => setSessions(null))
      .finally(() => setSessionsLoading(false))
  }, [selectedClient])

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

  const handleQueryKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && suggestions.length > 0) {
      onSelectClient(suggestions[0].common_name)
      setQuery('')
      setPickerOpen(false)
    }
    if (event.key === 'Escape') {
      setPickerOpen(false)
    }
  }

  return (
    <Card>
      <CardHeader className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <UserRound size={18} />
              Мониторинг клиента
            </CardTitle>
            <CardDescription>
              Выберите пользователя для детальной статистики, графика и лимитов трафика
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Switch
                id="traffic-focus-only"
                checked={focusOnly}
                onCheckedChange={onFocusOnlyChange}
                disabled={!selectedClient}
              />
              <Label htmlFor="traffic-focus-only" className="text-xs text-muted-foreground">
                Только выбранный
              </Label>
            </div>
            {selectedClient && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 gap-1 text-xs"
                onClick={() => {
                  onSelectClient('')
                  setQuery('')
                }}
              >
                <X size={14} />
                Сбросить
              </Button>
            )}
          </div>
        </div>

        <div ref={containerRef} className="relative">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setPickerOpen(true)
              }}
              onFocus={() => setPickerOpen(true)}
              onKeyDown={handleQueryKeyDown}
              placeholder={selectedClient ? `Сейчас: ${selectedClient} — найти другого...` : 'Поиск клиента по имени...'}
              className="h-10 pl-9 text-sm"
            />
          </div>
          {pickerOpen && suggestions.length > 0 && (
            <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border bg-popover p-1 shadow-md">
              {suggestions.map((row) => (
                <button
                  key={`${row.common_name}-${row.protocol_type}`}
                  type="button"
                  className={cn(
                    'flex w-full items-center justify-between gap-2 rounded-sm px-3 py-2 text-left text-sm hover:bg-accent',
                    selectedClient === row.common_name && 'bg-primary/10',
                  )}
                  onClick={() => {
                    onSelectClient(row.common_name)
                    setQuery('')
                    setPickerOpen(false)
                  }}
                >
                  <span className="min-w-0 truncate font-medium">{row.common_name}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    <Badge variant={getProtocolVariant(row.protocol_type)} className="text-[10px]">
                      {getProtocolLabel(row.protocol_type)}
                    </Badge>
                    <span className="mono text-[11px] text-muted-foreground tabular-nums">
                      {formatBytes(row.traffic_7d)} / 7д
                    </span>
                    <Badge variant={row.is_active ? 'success' : 'secondary'} className="text-[10px]">
                      {row.is_active ? 'Онлайн' : 'Офлайн'}
                    </Badge>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {!selectedRow ? (
          <EmptyState
            icon={Search}
            title="Клиент не выбран"
            description="Введите имя в поиске и нажмите Enter или выберите из списка подсказок"
            className="py-6"
          />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-lg font-semibold">{selectedRow.common_name}</h3>
              <Badge variant={getProtocolVariant(selectedRow.protocol_type)}>{getProtocolLabel(selectedRow.protocol_type)}</Badge>
              <Badge variant={selectedRow.is_active ? 'success' : 'secondary'}>
                {selectedRow.is_active ? 'Онлайн' : 'Офлайн'}
              </Badge>
              {policy?.traffic_limit_exceeded && (
                <Badge variant="destructive" className="gap-1">
                  <Gauge size={12} />
                  Лимит превышен
                </Badge>
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricTile
                label="Всего"
                value={formatBytes(selectedRow.total_bytes)}
                sub={`RX ${formatBytes(selectedRow.total_received)} · TX ${formatBytes(selectedRow.total_sent)}`}
              />
              <MetricTile label="За 1 день" value={formatBytes(selectedRow.traffic_1d)} />
              <MetricTile label="За 7 дней" value={formatBytes(selectedRow.traffic_7d)} />
              <MetricTile label="За 30 дней" value={formatBytes(selectedRow.traffic_30d)} />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-3 rounded-lg border p-4">
                <p className="text-sm font-medium">Разбивка VPN / AntiZapret</p>
                <SplitBar label="VPN" value={selectedRow.total_bytes_vpn} total={selectedRow.total_bytes} color={CHART_VPN} />
                <SplitBar
                  label="AntiZapret"
                  value={selectedRow.total_bytes_antizapret}
                  total={selectedRow.total_bytes}
                  color={CHART_ANTIZAPRET}
                />
                <div className="grid grid-cols-2 gap-3 pt-1 text-xs text-muted-foreground">
                  <span>
                    Подключений:{' '}
                    <strong className="text-foreground">
                      {sessions?.total_sessions ?? selectedRow.total_sessions}
                    </strong>
                    {sessions && sessions.unique_sources > 0 && (
                      <>
                        {' '}
                        · активных адресов:{' '}
                        <strong className="text-foreground">{activeSources.length}</strong>
                        {inactiveSources.length > 0 && (
                          <> из {sessions.unique_sources}</>
                        )}
                      </>
                    )}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Clock size={12} />
                    Последний раз: <strong className="text-foreground">{formatLastSeen(selectedRow.last_seen_at)}</strong>
                  </span>
                  {selectedRow.first_seen_at && (
                    <span className="col-span-2">
                      Первое появление: <strong className="text-foreground">{formatLastSeen(selectedRow.first_seen_at)}</strong>
                    </span>
                  )}
                  {sessionHint && (
                    <span className="col-span-2 text-[11px] text-amber-600 dark:text-amber-400">{sessionHint}</span>
                  )}
                </div>
              </div>

              <div className="space-y-3 rounded-lg border p-4">
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
                      <div className="h-2 overflow-hidden rounded-full bg-secondary">
                        <div
                          className={cn(
                            'h-full rounded-full transition-all duration-300',
                            policy.traffic_limit_exceeded ? 'bg-destructive' : 'bg-primary',
                          )}
                          style={{ width: `${limitPercent}%` }}
                        />
                      </div>
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

            <div className="space-y-3 rounded-lg border p-4">
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
                          <TableHead>VPN IP</TableHead>
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

            <div className="rounded-lg border">
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
                  <SelectTrigger className="h-9 w-[140px] text-xs">
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
                  <ResponsiveContainer width="100%" height={280}>
                    <AreaChart data={chartPoints} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="focusTrafficVpn" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={CHART_VPN} stopOpacity={0.35} />
                          <stop offset="95%" stopColor={CHART_VPN} stopOpacity={0.02} />
                        </linearGradient>
                        <linearGradient id="focusTrafficAz" x1="0" y1="0" x2="0" y2="1">
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
                        fill="url(#focusTrafficVpn)"
                        strokeWidth={2}
                        name="vpn"
                      />
                      <Area
                        type="monotone"
                        dataKey="antizapret"
                        stackId="1"
                        stroke={CHART_ANTIZAPRET}
                        fill="url(#focusTrafficAz)"
                        strokeWidth={2}
                        name="antizapret"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
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
          </>
        )}
      </CardContent>
    </Card>
  )
}
