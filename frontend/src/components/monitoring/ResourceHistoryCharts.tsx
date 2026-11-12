import { useMemo } from 'react'
import { Activity, Cpu, HardDrive, MemoryStick } from 'lucide-react'
import { CartesianGrid, Line, LineChart, Tooltip, YAxis } from 'recharts'
import { ChartResponsive } from '@/components/monitoring/ChartResponsive'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  CHART_COLORS,
  CHART_GRID,
  CHART_MARGIN,
  PercentAreaChart,
  RANGE_LABELS,
  TimeXAxis,
  formatChartLabel,
  type PercentAreaSeries,
  type ResourceChartPeriod,
} from '@/components/monitoring/resourceChartShared'
import type { ResourceHistory, ResourceHistoryPoint } from '@/types'

const PERCENT_SERIES: PercentAreaSeries[] = [
  { key: 'cpu', color: CHART_COLORS.cpu, name: 'cpu', gradientId: 'resCpu' },
  { key: 'memory', color: CHART_COLORS.ram, name: 'memory', gradientId: 'resRam' },
  { key: 'disk', color: CHART_COLORS.disk, name: 'disk', gradientId: 'resDisk' },
]

const PERCENT_LEGEND_LABELS: Record<string, string> = { cpu: 'CPU', memory: 'RAM', disk: 'Диск' }

type ResourceHistoryChartsProps = {
  data: ResourceHistory | null
  loading: boolean
  period: ResourceChartPeriod
  onPeriodChange: (period: ResourceChartPeriod) => void
  showLatestSummary?: boolean
  title?: string
  description?: string
}

function buildChartRows(points: ResourceHistoryPoint[], period: ResourceChartPeriod) {
  return points.map((p) => ({
    label: formatChartLabel(p.timestamp, period),
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
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity size={18} />
              {title}
            </CardTitle>
            <CardDescription>{cardDescription}</CardDescription>
          </div>
          <div className="grid w-full grid-cols-3 gap-1 sm:flex sm:w-auto sm:flex-wrap sm:items-center sm:gap-2">
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
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
                <PercentAreaChart
                  data={chartData}
                  height={280}
                  series={PERCENT_SERIES}
                  unit="%"
                  domain={[0, 100]}
                  legendLabels={PERCENT_LEGEND_LABELS}
                  hoverHighlight
                />
              </div>

              {chartData.some((p) => p.load_1 != null) && (
                <div>
                  <p className="mb-2 text-sm font-medium">Load average (1 мин)</p>
                  <ChartResponsive height={180}>
                    {({ width, height }) => (
                  <LineChart width={width} height={height} data={chartData} margin={CHART_MARGIN}>
                      <CartesianGrid {...CHART_GRID} />
                      <TimeXAxis />
                      <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={44} />
                      <Tooltip
                        cursor={{ stroke: 'hsl(var(--muted-foreground))', strokeWidth: 1, strokeDasharray: '4 4' }}
                        formatter={(value) => [Number(value ?? 0).toFixed(2), 'Load 1m']}
                        labelFormatter={(label) => `Время: ${label}`}
                      />
                      <Line
                        type="monotone"
                        dataKey="load_1"
                        name="load_1"
                        stroke={CHART_COLORS.load}
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
