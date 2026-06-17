import { BarChart3 } from 'lucide-react'
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
import EmptyState from '@/components/ui/EmptyState'
import { formatBytes } from './utils'

const CHART_RX = 'hsl(258, 65%, 58%)'
const CHART_TX = 'hsl(199, 72%, 48%)'

export interface WarperTrafficChartPoint {
  label: string
  rx: number
  tx: number
}

interface WarperTrafficChartProps {
  points: WarperTrafficChartPoint[]
  embedded?: boolean
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

  return (
    <ChartResponsive height={embedded ? 260 : 280}>
      {({ width, height }) => (
        <AreaChart width={width} height={height} data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="warperTrafficRx" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={CHART_RX} stopOpacity={0.35} />
              <stop offset="95%" stopColor={CHART_RX} stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="warperTrafficTx" x1="0" y1="0" x2="0" y2="1">
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
          <Tooltip
            formatter={(value: number, name: string) => [
              formatBytes(Number(value)),
              name === 'tx' ? 'Исходящий ↑' : 'Входящий ↓',
            ]}
            labelFormatter={(label) => `Период: ${label}`}
          />
          <Legend formatter={(value) => (value === 'tx' ? 'Исходящий ↑' : 'Входящий ↓')} />
          <Area
            type="monotone"
            dataKey="rx"
            stroke={CHART_RX}
            fill="url(#warperTrafficRx)"
            strokeWidth={2}
            name="rx"
          />
          <Area
            type="monotone"
            dataKey="tx"
            stroke={CHART_TX}
            fill="url(#warperTrafficTx)"
            strokeWidth={2}
            name="tx"
          />
        </AreaChart>
      )}
    </ChartResponsive>
  )
}
