import { useMemo } from 'react'
import { Activity, Cpu, HardDrive, MemoryStick } from 'lucide-react'
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
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate, formatDateTime, formatTime } from '@/lib/datetime'
import type { ResourceHistory, ResourceHistoryPoint } from '@/types'

const CHART_CPU = 'hsl(187, 72%, 45%)'
const CHART_RAM = 'hsl(142, 71%, 45%)'
const CHART_DISK = 'hsl(38, 92%, 50%)'
const CHART_LOAD = 'hsl(217, 33%, 55%)'

const RANGE_LABELS: Record<'1d' | '7d' | '30d', string> = {
  '1d': '1 день',
  '7d': '7 дней',
  '30d': '30 дней',
}

type Period = '1d' | '7d' | '30d'

type ResourceHistoryChartsProps = {
  data: ResourceHistory | null
  loading: boolean
  period: Period
  onPeriodChange: (period: Period) => void
  showLatestSummary?: boolean
  title?: string
  description?: string
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

function buildChartRows(points: ResourceHistoryPoint[], period: Period) {
  return points.map((p) => ({
    label: formatLabel(p.timestamp, period),
    cpu: p.cpu_percent,
    memory: p.memory_percent,
    disk: p.disk_percent,
    load_1: p.load_1 ?? null,
    memoryUsedGb: p.memory_used_mb / 1024,
    memoryTotalGb: p.memory_total_mb / 1024,
  }))
}

function latestPoint(points: ResourceHistoryPoint[]) {
  if (!points.length) return null
  return points[points.length - 1]
}

export default function ResourceHistoryCharts({
  data,
  loading,
  period,
  onPeriodChange,
  showLatestSummary = true,
  title = 'Ресурсы VPN-сервера',
  description,
}: ResourceHistoryChartsProps) {
  const chartData = useMemo(() => buildChartRows(data?.points ?? [], period), [data?.points, period])
  const latest = latestPoint(data?.points ?? [])
  const cardDescription =
    description ??
    `CPU, RAM и диск узла AntiZapret (OpenVPN, WireGuard, маршрутизация) · ${RANGE_LABELS[period]}${
      data && data.sample_count > 0 ? ` · ${data.sample_count} снимков` : ''
    }`

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity size={18} />
              {title}
            </CardTitle>
            <CardDescription>{cardDescription}</CardDescription>
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
            <Spinner label="Загрузка истории ресурсов..." className="py-12" />
          ) : !data || chartData.length === 0 ? (
            <EmptyState
              icon={Cpu}
              title="История ресурсов пока пуста"
              description="Снимки CPU/RAM/диска собираются фоновым worker панели каждую минуту. Подождите несколько минут после запуска панели или проверьте доступность узла."
              className="py-8"
            />
          ) : (
            <div className="space-y-6">
              {showLatestSummary && latest && (
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-lg border p-3">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Cpu size={14} />
                      CPU сейчас
                    </div>
                    <p className="mono mt-1 text-xl font-bold tabular-nums">{Math.round(latest.cpu_percent)}%</p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <MemoryStick size={14} />
                      RAM сейчас
                    </div>
                    <p className="mono mt-1 text-xl font-bold tabular-nums">
                      {Math.round(latest.memory_percent)}%
                      <span className="ml-1 text-sm font-normal text-muted-foreground">
                        ({(latest.memory_used_mb / 1024).toFixed(1)} / {(latest.memory_total_mb / 1024).toFixed(1)} GB)
                      </span>
                    </p>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <HardDrive size={14} />
                      Диск сейчас
                    </div>
                    <p className="mono mt-1 text-xl font-bold tabular-nums">{Math.round(latest.disk_percent)}%</p>
                  </div>
                </div>
              )}

              <div>
                <p className="mb-2 text-sm font-medium">Загрузка CPU / RAM / Диск (%)</p>
                <ChartResponsive height={280}>
                  {({ width, height }) => (
                <AreaChart width={width} height={height} data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="resCpu" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={CHART_CPU} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={CHART_CPU} stopOpacity={0.02} />
                      </linearGradient>
                      <linearGradient id="resRam" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={CHART_RAM} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={CHART_RAM} stopOpacity={0.02} />
                      </linearGradient>
                      <linearGradient id="resDisk" x1="0" y1="0" x2="0" y2="1">
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
                      cursor={{ stroke: 'hsl(var(--muted-foreground))', strokeWidth: 1, strokeDasharray: '4 4' }}
                      formatter={(value: number, name: string) => {
                        const labels: Record<string, string> = {
                          cpu: 'CPU',
                          memory: 'RAM',
                          disk: 'Диск',
                        }
                        return [`${Number(value).toFixed(1)}%`, labels[name] ?? name]
                      }}
                      labelFormatter={(label) => `Время: ${label}`}
                    />
                    <Legend
                      formatter={(value) =>
                        value === 'cpu' ? 'CPU' : value === 'memory' ? 'RAM' : 'Диск'
                      }
                    />
                    <Area
                      type="monotone"
                      dataKey="cpu"
                      name="cpu"
                      stroke={CHART_CPU}
                      fill="url(#resCpu)"
                      strokeWidth={2}
                      activeDot={{ r: 5, strokeWidth: 2, stroke: 'hsl(var(--background))' }}
                    />
                    <Area
                      type="monotone"
                      dataKey="memory"
                      name="memory"
                      stroke={CHART_RAM}
                      fill="url(#resRam)"
                      strokeWidth={2}
                      activeDot={{ r: 5, strokeWidth: 2, stroke: 'hsl(var(--background))' }}
                    />
                    <Area
                      type="monotone"
                      dataKey="disk"
                      name="disk"
                      stroke={CHART_DISK}
                      fill="url(#resDisk)"
                      strokeWidth={2}
                      activeDot={{ r: 5, strokeWidth: 2, stroke: 'hsl(var(--background))' }}
                    />
                  </AreaChart>
                  )}
                </ChartResponsive>
              </div>

              {chartData.some((p) => p.load_1 != null) && (
                <div>
                  <p className="mb-2 text-sm font-medium">Load average (1 мин)</p>
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
                      <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={44} />
                      <Tooltip
                        cursor={{ stroke: 'hsl(var(--muted-foreground))', strokeWidth: 1, strokeDasharray: '4 4' }}
                        formatter={(value: number) => [Number(value).toFixed(2), 'Load 1m']}
                        labelFormatter={(label) => `Время: ${label}`}
                      />
                      <Line
                        type="monotone"
                        dataKey="load_1"
                        name="load_1"
                        stroke={CHART_LOAD}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 5, strokeWidth: 2, stroke: 'hsl(var(--background))' }}
                      />
                    </LineChart>
                    )}
                  </ChartResponsive>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
