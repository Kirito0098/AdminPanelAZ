import { Area, AreaChart, CartesianGrid, Legend, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartResponsive } from '@/components/monitoring/ChartResponsive'
import { formatDate, formatDateTime, formatTime } from '@/lib/datetime'

/** Период графиков ресурсов — общий для сервера и панели. */
export type ResourceChartPeriod = '1d' | '7d' | '30d'

export const RANGE_LABELS: Record<ResourceChartPeriod, string> = {
  '1d': '1 день',
  '7d': '7 дней',
  '30d': '30 дней',
}

/** Палитра метрик: один и тот же показатель одного цвета на обоих экранах. */
export const CHART_COLORS = {
  cpu: 'hsl(187, 72%, 45%)',
  ram: 'hsl(142, 71%, 45%)',
  disk: 'hsl(38, 92%, 50%)',
  load: 'hsl(217, 33%, 55%)',
  total: 'hsl(217, 33%, 55%)',
  nginx: 'hsl(0, 62%, 50%)',
  watchdog: 'hsl(38, 92%, 50%)',
  vite: 'hsl(280, 65%, 55%)',
} as const

export const CHART_MARGIN = { top: 8, right: 8, left: 0, bottom: 0 }

export const CHART_GRID = { strokeDasharray: '3 3', opacity: 0.15, vertical: false }

/** Метка времени на оси X в зависимости от периода. */
export function formatChartLabel(ts: string, period: ResourceChartPeriod): string {
  if (period === '1d') {
    return formatTime(ts, { hour: '2-digit', minute: '2-digit' })
  }
  if (period === '7d') {
    return formatDateTime(ts, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  }
  return formatDate(ts, { day: '2-digit', month: '2-digit' })
}

/** Ось X с подписями по времени — одинаковая во всех графиках ресурсов. */
export function TimeXAxis() {
  return (
    <XAxis
      dataKey="label"
      tick={{ fontSize: 11 }}
      tickLine={false}
      axisLine={false}
      interval="preserveStartEnd"
    />
  )
}

export type PercentAreaSeries = {
  /** Поле строки данных. */
  key: string
  color: string
  /** Имя серии в Recharts: подпись в тултипе, если нет legendLabels. */
  name: string
  gradientId: string
  /** Верхняя точка градиента; нижняя всегда 0.02. */
  fillOpacity?: number
}

type PercentAreaChartProps = {
  data: Array<Record<string, unknown>>
  height: number
  series: PercentAreaSeries[]
  unit: string
  margin?: typeof CHART_MARGIN
  /** Подписи серий и включение легенды: key → текст. */
  legendLabels?: Record<string, string>
  /** Фиксированная шкала Y; без неё Recharts считает домен сам. */
  domain?: [number, number]
  /** Пунктирная вертикаль тултипа и увеличенная точка под курсором. */
  hoverHighlight?: boolean
}

/** Процентная area-диаграмма: CPU/RAM/диск на графиках ресурсов. */
export function PercentAreaChart({
  data,
  height,
  series,
  unit,
  margin = CHART_MARGIN,
  legendLabels,
  domain,
  hoverHighlight = false,
}: PercentAreaChartProps) {
  return (
    <ChartResponsive height={height}>
      {({ width, height: chartHeight }) => (
        <AreaChart width={width} height={chartHeight} data={data} margin={margin}>
          <defs>
            {series.map((item) => (
              <linearGradient key={item.gradientId} id={item.gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={item.color} stopOpacity={item.fillOpacity ?? 0.3} />
                <stop offset="95%" stopColor={item.color} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid {...CHART_GRID} />
          <TimeXAxis />
          <YAxis
            domain={domain}
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            unit={unit}
            width={44}
          />
          <Tooltip
            cursor={
              hoverHighlight
                ? { stroke: 'hsl(var(--muted-foreground))', strokeWidth: 1, strokeDasharray: '4 4' }
                : undefined
            }
            formatter={(value, name) => [
              `${Number(value ?? 0).toFixed(1)}${unit}`,
              legendLabels?.[String(name)] ?? String(name),
            ]}
            labelFormatter={(label) => `Время: ${label}`}
          />
          {legendLabels && <Legend formatter={(value) => legendLabels[String(value)] ?? String(value)} />}
          {series.map((item) => (
            <Area
              key={item.key}
              type="monotone"
              dataKey={item.key}
              name={item.name}
              stroke={item.color}
              fill={`url(#${item.gradientId})`}
              strokeWidth={2}
              activeDot={
                hoverHighlight ? { r: 5, strokeWidth: 2, stroke: 'hsl(var(--background))' } : undefined
              }
            />
          ))}
        </AreaChart>
      )}
    </ChartResponsive>
  )
}
