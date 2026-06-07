import { useEffect, useMemo, useState } from 'react'
import { Activity, Cpu, MemoryStick, Server } from 'lucide-react'
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
import { ApiError, getPanelResourceCurrent, getPanelResourceHistory } from '@/api/client'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useNotifications } from '@/context/NotificationContext'
import type { PanelResourceCurrent, PanelResourceHistory } from '@/types'

const CHART_CPU = 'hsl(187, 72%, 45%)'
const CHART_RAM = 'hsl(142, 71%, 45%)'
const CHART_TOTAL = 'hsl(217, 33%, 55%)'

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
  const d = new Date(ts)
  if (period === '1d') {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  if (period === '7d') {
    return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
}

function buildChartRows(points: PanelResourceHistory['points'], period: Period) {
  return points.map((p) => ({
    label: formatLabel(p.timestamp, period),
    cpu: p.backend_cpu_percent,
    memory: p.backend_memory_mb,
    total: p.total_panel_memory_mb,
    workers: p.backend_workers,
  }))
}

export default function PanelResourceHistoryCharts({
  period,
  onPeriodChange,
}: PanelResourceHistoryChartsProps) {
  const { error: notifyError } = useNotifications()
  const [history, setHistory] = useState<PanelResourceHistory | null>(null)
  const [current, setCurrent] = useState<PanelResourceCurrent | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [hist, live] = await Promise.all([
        getPanelResourceHistory(period),
        getPanelResourceCurrent(),
      ])
      setHistory(hist)
      setCurrent(live)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Ошибка загрузки ресурсов панели'
      notifyError(message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [period])

  const chartData = useMemo(() => buildChartRows(history?.points ?? [], period), [history?.points, period])
  const latest = history?.points?.length ? history.points[history.points.length - 1] : null

  return (
    <div className="space-y-4">
      <SettingsAlert variant="info" title="Что измеряется">
        Метрики процессов AdminPanelAZ на машине контроллера (где запущена панель):{' '}
        <strong>Backend (FastAPI/uvicorn)</strong> — CPU, RAM, число workers;{' '}
        <strong>Frontend</strong> — статические файлы, раздаёт backend (отдельного процесса в production нет).
        Опционально учитывается Nginx (если <code>BEHIND_NGINX=true</code>) и watchdog <code>start.sh</code>.
        Снимки пишутся каждые ~60 с, хранение 30 дней.
      </SettingsAlert>

      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server size={18} />
              Ресурсы панели AdminPanelAZ
            </CardTitle>
            <CardDescription>
              Backend (FastAPI/uvicorn) · {RANGE_LABELS[period]}
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
              {(current || latest) && (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-lg border p-3">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Cpu size={14} />
                      Backend CPU
                    </div>
                    <p className="mono mt-1 text-xl font-bold tabular-nums">
                      {Math.round(current?.backend_cpu_percent ?? latest?.backend_cpu_percent ?? 0)}%
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">FastAPI / uvicorn</p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <MemoryStick size={14} />
                      Backend RAM
                    </div>
                    <p className="mono mt-1 text-xl font-bold tabular-nums">
                      {current?.backend_memory_mb ?? latest?.backend_memory_mb ?? 0} MB
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      RSS {current?.backend_rss_mb ?? current?.backend_memory_mb ?? 0} MB
                    </p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Activity size={14} />
                      Workers
                    </div>
                    <p className="mono mt-1 text-xl font-bold tabular-nums">
                      {current?.backend_workers ?? latest?.backend_workers ?? 0}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">процессов uvicorn</p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Server size={14} />
                      Итого панель
                    </div>
                    <p className="mono mt-1 text-xl font-bold tabular-nums">
                      {current?.total_panel_memory_mb ?? latest?.total_panel_memory_mb ?? 0} MB
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {current?.frontend_note ?? 'Frontend — статика через backend'}
                    </p>
                  </div>
                </div>
              )}

              {current?.nginx_memory_mb != null && (
                <p className="text-xs text-muted-foreground">
                  Nginx (reverse proxy): {current.nginx_memory_mb} MB
                  {current.watchdog_memory_mb != null && (
                    <> · Watchdog start.sh: {current.watchdog_memory_mb} MB</>
                  )}
                </p>
              )}

              {current?.frontend_dev_memory_mb != null && (
                <SettingsAlert variant="warning" title="Режим разработки">
                  Обнаружен Vite dev-сервер ({current.frontend_dev_memory_mb} MB). В production frontend
                  раздаётся как статика через backend.
                </SettingsAlert>
              )}

              {!history || chartData.length === 0 ? (
                <EmptyState
                  icon={Cpu}
                  title="История ресурсов панели пока пуста"
                  description="Снимки CPU/RAM backend собираются фоновым worker каждую минуту. Подождите несколько минут после запуска панели."
                  className="py-8"
                />
              ) : (
                <>
                  <div>
                    <p className="mb-2 text-sm font-medium">Backend CPU (%)</p>
                    <ResponsiveContainer width="100%" height={220}>
                      <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
                          contentStyle={{
                            borderRadius: '8px',
                            border: '1px solid hsl(var(--border))',
                            background: 'hsl(var(--popover))',
                            fontSize: '12px',
                          }}
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
                    </ResponsiveContainer>
                  </div>

                  <div>
                    <p className="mb-2 text-sm font-medium">Backend RAM / Итого панель (MB)</p>
                    <ResponsiveContainer width="100%" height={220}>
                      <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
                              memory: 'Backend RAM',
                              total: 'Итого панель',
                            }
                            return [`${Number(value).toFixed(0)} MB`, labels[name] ?? name]
                          }}
                          labelFormatter={(label) => `Время: ${label}`}
                          contentStyle={{
                            borderRadius: '8px',
                            border: '1px solid hsl(var(--border))',
                            background: 'hsl(var(--popover))',
                            fontSize: '12px',
                          }}
                        />
                        <Legend
                          formatter={(value) =>
                            value === 'memory' ? 'Backend RAM' : value === 'total' ? 'Итого панель' : value
                          }
                          wrapperStyle={{ fontSize: '12px' }}
                        />
                        <Area
                          type="monotone"
                          dataKey="memory"
                          name="memory"
                          stroke={CHART_RAM}
                          fill="url(#panelRam)"
                          strokeWidth={2}
                        />
                        <Area
                          type="monotone"
                          dataKey="total"
                          name="total"
                          stroke={CHART_TOTAL}
                          fill="url(#panelTotal)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
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
