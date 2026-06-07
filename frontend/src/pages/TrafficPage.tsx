import { useCallback, useEffect, useState } from 'react'
import { Activity, BarChart3, Database, Users } from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  ApiError,
  getTrafficChart,
  getTrafficOverview,
  resetTraffic,
} from '@/api/client'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import MetricCard from '@/components/noc/MetricCard'
import { NodeBadge } from '@/components/NodeSelector'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import Spinner from '@/components/ui/Spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useAuth } from '@/context/AuthContext'
import type { TrafficChartData, TrafficOverview } from '@/types'

const REFRESH_INTERVAL = 60

export default function TrafficPage() {
  const { activeNode } = useNode()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal } = useProgress()
  const [data, setData] = useState<TrafficOverview | null>(null)
  const [chartData, setChartData] = useState<TrafficChartData | null>(null)
  const [selectedClient, setSelectedClient] = useState<string>('')
  const [chartRange, setChartRange] = useState('7d')
  const [loading, setLoading] = useState(true)
  const [chartLoading, setChartLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)

  const load = useCallback(async (initial = false) => {
    if (initial) {
      setLoading(true)
      startGlobal()
    }
    try {
      const overview = await getTrafficOverview()
      setData(overview)
      if (!selectedClient && overview.rows.length > 0) {
        setSelectedClient(overview.rows[0].common_name)
      }
      setCountdown(REFRESH_INTERVAL)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки трафика')
    } finally {
      setLoading(false)
      if (initial) doneGlobal()
    }
  }, [startGlobal, doneGlobal, notifyError, selectedClient])

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

  const chartPoints =
    chartData?.labels.map((label, i) => ({
      label,
      vpn: chartData.vpn_bytes[i] ?? 0,
      antizapret: chartData.antizapret_bytes[i] ?? 0,
      total: (chartData.vpn_bytes[i] ?? 0) + (chartData.antizapret_bytes[i] ?? 0),
    })) ?? []

  if (loading && !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner />
      </div>
    )
  }

  const summary = data?.summary

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Мониторинг трафика</h2>
          <p className="text-sm text-muted-foreground">Накопленная статистика RX/TX по клиентам VPN и Antizapret</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <NodeBadge />
          {summary?.db_is_stale && (
            <Badge variant="outline" className="border-amber-500 text-amber-600">
              БД устарела ({summary.db_age_seconds}с)
            </Badge>
          )}
          <AutoRefreshControl
            enabled={autoRefresh}
            countdown={countdown}
            interval={REFRESH_INTERVAL}
            onToggle={() => setAutoRefresh((v) => !v)}
            onRefresh={() => load()}
          />
          {isAdmin && (
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  await resetTraffic('all')
                  success('Статистика сброшена')
                  load()
                } catch (err) {
                  notifyError(err instanceof ApiError ? err.message : 'Ошибка сброса')
                }
              }}
            >
              Сбросить статистику
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="Клиентов" value={summary?.users_count ?? 0} icon={Users} subtitle={`активных: ${summary?.active_users_count ?? 0}`} />
        <MetricCard title="Получено (RX)" value={formatBytes(summary?.total_received ?? 0)} icon={Activity} />
        <MetricCard title="Отправлено (TX)" value={formatBytes(summary?.total_sent ?? 0)} icon={BarChart3} />
        <MetricCard
          title="БД"
          value={summary?.db_is_stale ? 'Устарела' : 'Актуальна'}
          icon={Database}
          subtitle={summary?.latest_sample_at ? new Date(summary.latest_sample_at).toLocaleString('ru') : 'нет данных'}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>График трафика</CardTitle>
            <CardDescription>Дельта байт по времени для выбранного клиента</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-3">
              <Select value={selectedClient} onValueChange={setSelectedClient}>
                <SelectTrigger className="w-48">
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
                <SelectTrigger className="w-32">
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
            {chartLoading ? (
              <div className="flex h-48 items-center justify-center">
                <Spinner />
              </div>
            ) : chartPoints.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartPoints}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v) => formatBytes(v)} tick={{ fontSize: 11 }} width={70} />
                  <Tooltip formatter={(v: number) => formatBytes(v)} />
                  <Legend />
                  <Area type="monotone" dataKey="vpn" stackId="1" stroke="hsl(var(--primary))" fill="hsl(var(--primary))" fillOpacity={0.3} name="VPN" />
                  <Area type="monotone" dataKey="antizapret" stackId="1" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.3} name="Antizapret" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">Нет данных за выбранный период</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Топ клиентов (7д)</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={[...(data?.rows ?? [])]
                  .sort((a, b) => b.traffic_7d - a.traffic_7d)
                  .slice(0, 8)
                  .map((r) => ({ name: r.common_name, traffic: r.traffic_7d }))}
              >
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                <YAxis tickFormatter={(v) => formatBytes(v)} tick={{ fontSize: 11 }} width={70} />
                <Tooltip formatter={(v: number) => formatBytes(v)} />
                <Bar dataKey="traffic" fill="hsl(var(--primary))" name="7 дней" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Таблица трафика (БД)</CardTitle>
          <CardDescription>Накопленные RX/TX, окна 1д / 7д / 30д</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Клиент</TableHead>
                <TableHead>Протокол</TableHead>
                <TableHead className="text-right">RX</TableHead>
                <TableHead className="text-right">TX</TableHead>
                <TableHead className="text-right">1д</TableHead>
                <TableHead className="text-right">7д</TableHead>
                <TableHead className="text-right">30д</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.rows.map((r) => (
                <TableRow
                  key={`${r.common_name}-${r.protocol_type}`}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => setSelectedClient(r.common_name)}
                >
                  <TableCell className="font-medium">{r.common_name}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{r.protocol_type}</Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatBytes(r.total_received)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatBytes(r.total_sent)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatBytes(r.traffic_1d)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatBytes(r.traffic_7d)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatBytes(r.traffic_30d)}</TableCell>
                  <TableCell>
                    <Badge variant={r.is_active ? 'default' : 'secondary'}>{r.is_active ? 'Онлайн' : 'Офлайн'}</Badge>
                  </TableCell>
                </TableRow>
              ))}
              {(!data?.rows || data.rows.length === 0) && (
                <TableRow>
                  <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                    Нет накопленной статистики. Коллектор запускается автоматически каждые 30с.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
