import { BarChart3 } from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ChartResponsive } from '@/components/monitoring/ChartResponsive'
import EmptyState from '@/components/ui/EmptyState'
import { formatBytes } from './utils'

const CHART_RX = 'hsl(258, 65%, 58%)'
const CHART_TX = 'hsl(199, 72%, 48%)'
const CHART_HEIGHT = 280

export interface WarperTrafficChartPoint {
  label: string
  rx: number
  tx: number
}

interface WarperTrafficChartProps {
  points: WarperTrafficChartPoint[]
  embedded?: boolean
}

function chartLegend(value: string) {
  return value === 'tx' ? 'Исходящий ↑' : 'Входящий ↓'
}

function chartTooltip(value: number, name: string) {
  return [formatBytes(Number(value)), name === 'tx' ? 'Исходящий ↑' : 'Входящий ↓']
}

export default function WarperTrafficChart({ points, embedded = false }: WarperTrafficChartProps) {
  if (points.length === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="Нет данных для графика"
        description="Статистика накапливается по часам в traffic.json на узле. Появится после работы sing-box."
        className={embedded ? 'py-8' : 'py-10'}
      />
    )
  }

  const useBars = points.length <= 2
  const chartId = useBars ? 'warperTrafficBar' : 'warperTrafficArea'

  return (
    <ChartResponsive height={CHART_HEIGHT} className="h-[280px]">
      {({ width, height }) =>
        useBars ? (
          <BarChart
            width={width}
            height={height}
            data={points}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
            barCategoryGap="20%"
          >
            <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tickFormatter={(value) => formatBytes(Number(value))}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={64}
            />
            <Tooltip formatter={chartTooltip} labelFormatter={(label) => `Период: ${label}`} />
            <Legend formatter={chartLegend} />
            <Bar dataKey="rx" fill={CHART_RX} name="rx" radius={[4, 4, 0, 0]} maxBarSize={48} />
            <Bar dataKey="tx" fill={CHART_TX} name="tx" radius={[4, 4, 0, 0]} maxBarSize={48} />
          </BarChart>
        ) : (
          <AreaChart
            width={width}
            height={height}
            data={points}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id={`${chartId}Rx`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={CHART_RX} stopOpacity={0.35} />
                <stop offset="95%" stopColor={CHART_RX} stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id={`${chartId}Tx`} x1="0" y1="0" x2="0" y2="1">
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
              tickFormatter={(value) => formatBytes(Number(value))}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={64}
            />
            <Tooltip formatter={chartTooltip} labelFormatter={(label) => `Период: ${label}`} />
            <Legend formatter={chartLegend} />
            <Area
              type="monotone"
              dataKey="rx"
              stroke={CHART_RX}
              fill={`url(#${chartId}Rx)`}
              strokeWidth={2}
              name="rx"
            />
            <Area
              type="monotone"
              dataKey="tx"
              stroke={CHART_TX}
              fill={`url(#${chartId}Tx)`}
              strokeWidth={2}
              name="tx"
            />
          </AreaChart>
        )
      }
    </ChartResponsive>
  )
}
