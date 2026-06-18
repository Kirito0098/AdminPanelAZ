import { useEffect, useMemo, useState } from 'react'
import { Activity, Cpu, HardDrive, MemoryStick, Server } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ChartResponsive } from '@/components/monitoring/ChartResponsive'
import { ApiError, getPanelResourceCurrent, getPanelResourceHistory } from '@/api/client'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useNotifications } from '@/context/NotificationContext'
import { formatDate, formatDateTime, formatTime } from '@/lib/datetime'
import type { PanelResourceCurrent, PanelResourceHistory, PanelResourceHistoryPoint } from '@/types'

const CHART_CPU = 'hsl(187, 72%, 45%)'
const CHART_RAM = 'hsl(142, 71%, 45%)'
const CHART_DISK = 'hsl(38, 92%, 50%)'
const CHART_TOTAL = 'hsl(217, 33%, 55%)'
const CHART_NGINX = 'hsl(0, 62%, 50%)'
const CHART_WATCHDOG = 'hsl(38, 92%, 50%)'
const CHART_VITE = 'hsl(280, 65%, 55%)'
const CHART_LOAD = 'hsl(217, 33%, 55%)'

const RANGE_LABELS: Record<'1d' | '7d' | '30d', string> = {
  '1d': '1 день',
  '7d': '7 дней',
  '30d': '30 дней',
}

type Period = '1d' | '7d' | '30d'

type PanelResourceHistoryChartsProps = {
  period: Period
  onPeriodChange: (period: Period) => void
}

function formatLabel(ts: string, period: Period) {
  if (period === '1d') {
    return formatTime(ts, { hour: '2-digit', minute: '2-digit' })
  }
  if (period === '7d') {
    return formatDateTime(ts, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  }
  return formatDate(ts, { day: '2-digit', month: '2-digit' })
}

function buildChartRows(points: PanelResourceHistoryPoint[], period: Period) {
  return points.map((p) => ({
    label: formatLabel(p.timestamp, period),
    cpu: p.backend_cpu_percent,
    memory: p.backend_memory_mb,
    nginx: p.nginx_memory_mb ?? 0,
    watchdog: p.watchdog_memory_mb ?? 0,
    vite: p.frontend_dev_memory_mb ?? 0,
    total: p.total_panel_memory_mb,
    workers: p.backend_workers,
    hostCpu: p.host_cpu_percent,
    hostMemory: p.host_memory_percent,
    hostDisk: p.host_disk_percent,
    hostLoad: p.host_load_1 ?? null,
  }))
}

function periodStats(points: PanelResourceHistoryPoint[]) {
  if (!points.length) return null
  const cpus = points.map((p) => p.backend_cpu_percent)
  const totals = points.map((p) => p.total_panel_memory_mb)
  const hostCpus = points.map((p) => p.host_cpu_percent)
  return {
    backendCpuAvg: cpus.reduce((a, b) => a + b, 0) / cpus.length,
    backendCpuMax: Math.max(...cpus),
    totalMemAvg: totals.reduce((a, b) => a + b, 0) / totals.length,
    totalMemMax: Math.max(...totals),
    hostCpuAvg: hostCpus.reduce((a, b) => a + b, 0) / hostCpus.length,
    hostCpuMax: Math.max(...hostCpus),
  }
}

function hasHostHistory(points: PanelResourceHistoryPoint[]) {
  return points.some((p) => p.host_cpu_percent > 0 || p.host_memory_percent > 0)
}

function hasNginxHistory(points: PanelResourceHistoryPoint[]) {
  return points.some((p) => p.nginx_memory_mb != null && p.nginx_memory_mb > 0)
}

function hasWatchdogHistory(points: PanelResourceHistoryPoint[]) {
  return points.some((p) => p.watchdog_memory_mb != null && p.watchdog_memory_mb > 0)
}

function hasViteHistory(points: PanelResourceHistoryPoint[]) {
  return points.some((p) => p.frontend_dev_memory_mb != null && p.frontend_dev_memory_mb > 0)
}

function sumLiveComponents(live: PanelResourceCurrent) {
  return (
    live.backend_memory_mb +
    (live.nginx_memory_mb ?? 0) +
    (live.watchdog_memory_mb ?? 0) +
    (live.frontend_dev_memory_mb ?? 0)
  )
}

export default function PanelResourceHistoryCharts({
  period,
  onPeriodChange,
}: PanelResourceHistoryChartsProps) {
  const { error: notifyError } = useNotifications()
  const [history, setHistory] = useState<PanelResourceHistory | null>(null)
  const [current, setCurrent] = useState<PanelResourceCurrent | null>(null)
  const [loading, setLoading] = useState(true)

  const loadHistory = async () => {
    setLoading(true)
    try {
      const hist = await getPanelResourceHistory(period)
      setHistory(hist)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Ошибка загрузки истории ресурсов панели'
      notifyError(message)
    } finally {
      setLoading(false)
    }
  }

  const loadCurrent = async () => {
    try {
      const live = await getPanelResourceCurrent()
      setCurrent(live)
    } catch {
      // live refresh is best-effort
    }
  }

  useEffect(() => {
    loadHistory()
  }, [period])

  useEffect(() => {
    loadCurrent()
    const timer = window.setInterval(loadCurrent, 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const chartData = useMemo(() => buildChartRows(history?.points ?? [], period), [history?.points, period])
  const latest = history?.points?.length ? history.points[history.points.length - 1] : null
  const stats = useMemo(() => periodStats(history?.points ?? []), [history?.points])
  const showHostCharts = hasHostHistory(history?.points ?? [])
  const showNginxChart = hasNginxHistory(history?.points ?? [])
  const showWatchdogChart = hasWatchdogHistory(history?.points ?? [])
  const showViteChart = hasViteHistory(history?.points ?? [])

  const live = current
  const snap = latest

  return (
    <div className="space-y-4">
      <SettingsAlert variant="info" title="Что измеряется">
        На машине контроллера (где запущена панель):{' '}
        <strong>процессы AdminPanelAZ</strong> — Backend, Nginx, watchdog <code>start.sh</code>, при разработке также Vite (
        <code>npm run dev</code>). <strong>Итого</strong> — сумма этих процессов, не RAM всего сервера.{' '}
        <strong>Ресурсы хоста</strong> — CPU/RAM/диск всей машины. Снимки ~60 с, хранение 30 дней.
      </SettingsAlert>

      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server size={18} />
              Ресурсы панели AdminPanelAZ
            </CardTitle>
            <CardDescription>
              {live?.host_hostname ? `${live.host_hostname} · ` : ''}
              uptime {live?.host_uptime || '—'} · {RANGE_LABELS[period]}
              {history && history.sample_count > 0 && <> · {history.sample_count} снимков</>}
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {(['1d', '7d', '30d'] as const).map((r) => (
              <Button
                key={r}
                size="sm"
                variant={period === r ? 'default' : 'outline'}
                onClick={() => onPeriodChange(r)}
              >
                {RANGE_LABELS[r]}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Spinner label="Загрузка ресурсов панели..." className="py-12" />
          ) : (
            <div className="space-y-6">
              {(live || snap) && (
                <>
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Процессы панели
                    </p>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <div className="rounded-lg border p-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Cpu size={14} />
                          Backend CPU
                        </div>
                        <p className="mono mt-1 text-xl font-bold tabular-nums">
                          {Math.round(live?.backend_cpu_percent ?? snap?.backend_cpu_percent ?? 0)}%
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">FastAPI / uvicorn</p>
                      </div>
                      <div className="rounded-lg border p-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <MemoryStick size={14} />
                          Backend RAM
                        </div>
                        <p className="mono mt-1 text-xl font-bold tabular-nums">
                          {live?.backend_memory_mb ?? snap?.backend_memory_mb ?? 0} MB
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          RSS {live?.backend_rss_mb ?? live?.backend_memory_mb ?? 0} MB
                        </p>
                      </div>
                      <div className="rounded-lg border p-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Activity size={14} />
                          Workers
                        </div>
                        <p className="mono mt-1 text-xl font-bold tabular-nums">
                          {live?.backend_workers ?? snap?.backend_workers ?? 0}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">процессов uvicorn</p>
                      </div>
                      <div className="rounded-lg border p-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Server size={14} />
                          Итого панель
                        </div>
                        <p className="mono mt-1 text-xl font-bold tabular-nums">
                          {live?.total_panel_memory_mb ?? snap?.total_panel_memory_mb ?? 0} MB
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {live?.frontend_note ?? 'Frontend — статика через backend'}
                          {live && <> · сумма компонентов {sumLiveComponents(live)} MB</>}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Машина контроллера
                    </p>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <div className="rounded-lg border p-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Cpu size={14} />
                          CPU хоста
                        </div>
                        <p className="mono mt-1 text-xl font-bold tabular-nums">
                          {Math.round(live?.host_cpu_percent ?? snap?.host_cpu_percent ?? 0)}%
                        </p>
                        {live?.host_load_1 != null && (
                          <p className="mt-1 text-xs text-muted-foreground">load {live.host_load_1.toFixed(2)}</p>
                        )}
                      </div>
                      <div className="rounded-lg border p-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <MemoryStick size={14} />
                          RAM хоста
                        </div>
                        <p className="mono mt-1 text-xl font-bold tabular-nums">
                          {Math.round(live?.host_memory_percent ?? snap?.host_memory_percent ?? 0)}%
                          <span className="ml-1 text-sm font-normal text-muted-foreground">
                            ({((live?.host_memory_used_mb ?? snap?.host_memory_used_mb ?? 0) / 1024).toFixed(1)} /{' '}
                            {((live?.host_memory_total_mb ?? snap?.host_memory_total_mb ?? 0) / 1024).toFixed(1)} GB)
                          </span>
                        </p>
                      </div>
                      <div className="rounded-lg border p-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <HardDrive size={14} />
                          Диск хоста
                        </div>
                        <p className="mono mt-1 text-xl font-bold tabular-nums">
                          {Math.round(live?.host_disk_percent ?? snap?.host_disk_percent ?? 0)}%
                        </p>
                      </div>
                      {(live?.nginx_memory_mb != null ||
                        live?.watchdog_memory_mb != null ||
                        snap?.nginx_memory_mb != null ||
                        snap?.watchdog_memory_mb != null) && (
                        <div className="rounded-lg border p-3">
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Server size={14} />
                            Доп. процессы
                          </div>
                          <p className="mono mt-1 text-sm font-semibold tabular-nums">
                            {live?.nginx_memory_mb != null && <>Nginx {live.nginx_memory_mb} MB</>}
                            {live?.nginx_memory_mb != null && live?.watchdog_memory_mb != null && ' · '}
                            {live?.watchdog_memory_mb != null && <>Watchdog {live.watchdog_memory_mb} MB</>}
                            {live?.frontend_dev_memory_mb != null && (
                              <>
                                {(live?.nginx_memory_mb != null || live?.watchdog_memory_mb != null) && ' · '}
                                Vite {live.frontend_dev_memory_mb} MB
                              </>
                            )}
                            {live?.nginx_memory_mb == null &&
                              live?.watchdog_memory_mb == null &&
                              snap?.nginx_memory_mb != null &&
                              <>Nginx {snap.nginx_memory_mb} MB</>}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}

              {live?.frontend_dev_memory_mb != null && (
                <SettingsAlert variant="warning" title="Режим разработки">
                  Обнаружен Vite dev-сервер ({live.frontend_dev_memory_mb} MB). В production frontend раздаётся как
                  статика через backend.
                </SettingsAlert>
              )}

              {stats && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <div className="rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                    Backend CPU · {RANGE_LABELS[period]}: среднее{' '}
                    <span className="mono font-medium text-foreground">{stats.backendCpuAvg.toFixed(1)}%</span>, пик{' '}
                    <span className="mono font-medium text-foreground">{stats.backendCpuMax.toFixed(1)}%</span>
                  </div>
                  <div className="rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                    Итого RAM панели · {RANGE_LABELS[period]}: среднее{' '}
                    <span className="mono font-medium text-foreground">{Math.round(stats.totalMemAvg)} MB</span>, пик{' '}
                    <span className="mono font-medium text-foreground">{stats.totalMemMax} MB</span>
                  </div>
                  {showHostCharts && (
                    <div className="rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                      CPU хоста · {RANGE_LABELS[period]}: среднее{' '}
                      <span className="mono font-medium text-foreground">{stats.hostCpuAvg.toFixed(1)}%</span>, пик{' '}
                      <span className="mono font-medium text-foreground">{stats.hostCpuMax.toFixed(1)}%</span>
                    </div>
                  )}
                </div>
              )}

              {!history || chartData.length === 0 ? (
                <EmptyState
                  icon={Cpu}
                  title="История ресурсов панели пока пуста"
                  description="Снимки CPU/RAM backend и хоста собираются фоновым worker каждую минуту. Подождите несколько минут после запуска панели."
                  className="py-8"
                />
              ) : (
                <>
                  {showHostCharts && (
                    <div>
                      <p className="mb-2 text-sm font-medium">Хост контроллера: CPU / RAM / Диск (%)</p>
                      <ChartResponsive height={240}>
                        {({ width, height }) => (
                        <AreaChart width={width} height={height} data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                          <defs>
                            <linearGradient id="panelHostCpu" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor={CHART_CPU} stopOpacity={0.3} />
                              <stop offset="95%" stopColor={CHART_CPU} stopOpacity={0.02} />
                            </linearGradient>
                            <linearGradient id="panelHostRam" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor={CHART_RAM} stopOpacity={0.3} />
                              <stop offset="95%" stopColor={CHART_RAM} stopOpacity={0.02} />
                            </linearGradient>
                            <linearGradient id="panelHostDisk" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor={CHART_DISK} stopOpacity={0.3} />
                              <stop offset="95%" stopColor={CHART_DISK} stopOpacity={0.02} />
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
                            domain={[0, 100]}
                            tick={{ fontSize: 11 }}
                            tickLine={false}
                            axisLine={false}
                            unit="%"
                            width={44}
                          />
                          <Tooltip
                            formatter={(value: number, name: string) => {
                              const labels: Record<string, string> = {
                                hostCpu: 'CPU',
                                hostMemory: 'RAM',
                                hostDisk: 'Диск',
                              }
                              return [`${Number(value).toFixed(1)}%`, labels[name] ?? name]
                            }}
                            labelFormatter={(label) => `Время: ${label}`}
                          />
                          <Legend
                            formatter={(value) =>
                              value === 'hostCpu' ? 'CPU' : value === 'hostMemory' ? 'RAM' : 'Диск'
                            }
                          />
                          <Area
                            type="monotone"
                            dataKey="hostCpu"
                            name="hostCpu"
                            stroke={CHART_CPU}
                            fill="url(#panelHostCpu)"
                            strokeWidth={2}
                          />
                          <Area
                            type="monotone"
                            dataKey="hostMemory"
                            name="hostMemory"
                            stroke={CHART_RAM}
                            fill="url(#panelHostRam)"
                            strokeWidth={2}
                          />
                          <Area
                            type="monotone"
                            dataKey="hostDisk"
                            name="hostDisk"
                            stroke={CHART_DISK}
                            fill="url(#panelHostDisk)"
                            strokeWidth={2}
                          />
                        </AreaChart>
                        )}
                      </ChartResponsive>
                    </div>
                  )}

                  <div>
                    <p className="mb-2 text-sm font-medium">Backend CPU (%)</p>
                    <ChartResponsive height={220}>
                      {({ width, height }) => (
                    <AreaChart width={width} height={height} data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="panelCpu" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={CHART_CPU} stopOpacity={0.3} />
                            <stop offset="95%" stopColor={CHART_CPU} stopOpacity={0.02} />
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
                        <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} unit="%" width={44} />
                        <Tooltip
                          formatter={(value: number) => [`${Number(value).toFixed(1)}%`, 'CPU']}
                          labelFormatter={(label) => `Время: ${label}`}
                        />
                        <Area
                          type="monotone"
                          dataKey="cpu"
                          name="cpu"
                          stroke={CHART_CPU}
                          fill="url(#panelCpu)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                      )}
                    </ChartResponsive>
                  </div>

                  <div>
                    <p className="mb-2 text-sm font-medium">Память процессов панели (MB)</p>
                    <ChartResponsive height={240}>
                      {({ width, height }) => (
                    <AreaChart width={width} height={height} data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="panelRam" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={CHART_RAM} stopOpacity={0.3} />
                            <stop offset="95%" stopColor={CHART_RAM} stopOpacity={0.02} />
                          </linearGradient>
                          <linearGradient id="panelTotal" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={CHART_TOTAL} stopOpacity={0.2} />
                            <stop offset="95%" stopColor={CHART_TOTAL} stopOpacity={0.02} />
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
                        <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} unit="MB" width={52} />
                        <Tooltip
                          formatter={(value: number, name: string) => {
                            const labels: Record<string, string> = {
                              memory: 'Backend',
                              nginx: 'Nginx',
                              watchdog: 'Watchdog',
                              vite: 'Vite dev',
                              total: 'Итого',
                            }
                            return [`${Number(value).toFixed(0)} MB`, labels[name] ?? name]
                          }}
                          labelFormatter={(label) => `Время: ${label}`}
                        />
                        <Legend
                          formatter={(value) => {
                            const labels: Record<string, string> = {
                              memory: 'Backend',
                              nginx: 'Nginx',
                              watchdog: 'Watchdog',
                              vite: 'Vite dev',
                              total: 'Итого',
                            }
                            return labels[value] ?? value
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="memory"
                          name="memory"
                          stroke={CHART_RAM}
                          fill="url(#panelRam)"
                          strokeWidth={2}
                        />
                        {showNginxChart && (
                          <Area
                            type="monotone"
                            dataKey="nginx"
                            name="nginx"
                            stroke={CHART_NGINX}
                            fill="none"
                            strokeWidth={2}
                            strokeDasharray="4 4"
                          />
                        )}
                        {showWatchdogChart && (
                          <Area
                            type="monotone"
                            dataKey="watchdog"
                            name="watchdog"
                            stroke={CHART_WATCHDOG}
                            fill="none"
                            strokeWidth={2}
                            strokeDasharray="4 4"
                          />
                        )}
                        {showViteChart && (
                          <Area
                            type="monotone"
                            dataKey="vite"
                            name="vite"
                            stroke={CHART_VITE}
                            fill="none"
                            strokeWidth={2}
                            strokeDasharray="4 4"
                          />
                        )}
                        <Area
                          type="monotone"
                          dataKey="total"
                          name="total"
                          stroke={CHART_TOTAL}
                          fill="url(#panelTotal)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                      )}
                    </ChartResponsive>
                  </div>

                  <div>
                    <p className="mb-2 text-sm font-medium">Workers uvicorn</p>
                    <ChartResponsive height={180}>
                      {({ width, height }) => (
                    <LineChart width={width} height={height} data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
                        <XAxis
                          dataKey="label"
                          tick={{ fontSize: 11 }}
                          tickLine={false}
                          axisLine={false}
                          interval="preserveStartEnd"
                        />
                        <YAxis
                          allowDecimals={false}
                          tick={{ fontSize: 11 }}
                          tickLine={false}
                          axisLine={false}
                          width={36}
                        />
                        <Tooltip
                          formatter={(value: number) => [value, 'Workers']}
                          labelFormatter={(label) => `Время: ${label}`}
                        />
                        <Line
                          type="monotone"
                          dataKey="workers"
                          name="workers"
                          stroke={CHART_LOAD}
                          strokeWidth={2}
                          dot={false}
                        />
                      </LineChart>
                      )}
                    </ChartResponsive>
                  </div>
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
