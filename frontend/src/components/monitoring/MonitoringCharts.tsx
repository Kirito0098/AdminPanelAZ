import { useEffect, useMemo, useState } from 'react'
import { BarChart3, TrendingUp } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ChartResponsive } from '@/components/monitoring/ChartResponsive'
import { formatTime } from '@/lib/datetime'
import { isWireGuardOnline } from '@/lib/wireguardStatus'
import MonitoringChartCard, { MonitoringChartEmpty } from '@/components/monitoring/MonitoringChartCard'
import {
  MONITORING_CHART_HEIGHT,
  MONITORING_PROTOCOL_COLORS,
  monitoringChartTooltipProps,
  getProtocolBarColor,
} from '@/components/monitoring/monitoringChartTheme'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { ConnectionHistoryPoint, MonitoringOverview } from '@/types'

interface HistoryPoint {
  time: string
  connections: number
  ovpn: number
  wg: number
}

interface MonitoringChartsProps {
  data: MonitoringOverview
  serverHistory?: ConnectionHistoryPoint[]
  historyPeriod?: '1h' | '6h' | '24h'
  onHistoryPeriodChange?: (period: '1h' | '6h' | '24h') => void
  historyLoading?: boolean
}

function formatBytes(n: number) {
  const unit = '\u00A0'
  if (n < 1024) return `${n}${unit}B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)}${unit}KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)}${unit}MB`
  if (n < 1024 ** 4) return `${(n / 1024 ** 3).toFixed(2)}${unit}GB`
  return `${(n / 1024 ** 4).toFixed(2)}${unit}TB`
}

function totalTraffic(data: MonitoringOverview) {
  const ovpn = data.openvpn_clients.reduce((s, c) => s + c.bytes_received + c.bytes_sent, 0)
  const wg = data.wireguard_peers.reduce((s, p) => s + p.transfer_rx + p.transfer_tx, 0)
  return ovpn + wg
}

export default function MonitoringCharts({
  data,
  serverHistory,
  historyPeriod = '1h',
  onHistoryPeriodChange,
  historyLoading = false,
}: MonitoringChartsProps) {
  const [liveTail, setLiveTail] = useState<HistoryPoint[]>([])

  useEffect(() => {
    const wgActive = data.wireguard_peers.filter(isWireGuardOnline).length
    const point: HistoryPoint = {
      time: formatTime(data.timestamp, { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      connections: data.openvpn_clients.length + wgActive,
      ovpn: data.openvpn_clients.length,
      wg: wgActive,
    }
    setLiveTail((prev) => {
      const last = prev[prev.length - 1]
      if (last && last.time === point.time) return prev
      return [...prev.slice(-4), point]
    })
  }, [data])

  const serverPoints: HistoryPoint[] = useMemo(() => {
    if (!serverHistory?.length) return []
    return serverHistory.map((p) => ({
      time: formatTime(p.timestamp, { hour: '2-digit', minute: '2-digit' }),
      connections: p.total,
      ovpn: p.openvpn,
      wg: p.wireguard,
    }))
  }, [serverHistory])

  const history = serverPoints.length >= 2 ? serverPoints : liveTail

  const connectionsBar = useMemo(() => {
    const wgActive = data.wireguard_peers.filter(isWireGuardOnline).length
    return [
      { name: 'OpenVPN', count: data.openvpn_clients.length },
      { name: 'WireGuard', count: wgActive },
    ]
  }, [data])

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <MonitoringChartCard
        title="Подключения во времени"
        description={
          serverPoints.length >= 2
            ? `Серверная история · ${historyPeriod}`
            : 'Локальный хвост (ожидание серверных точек)'
        }
        icon={TrendingUp}
        actions={
          onHistoryPeriodChange ? (
            <Select
              value={historyPeriod}
              onValueChange={(v) => onHistoryPeriodChange(v as '1h' | '6h' | '24h')}
            >
              <SelectTrigger className="h-7 w-[88px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1h">1ч</SelectItem>
                <SelectItem value="6h">6ч</SelectItem>
                <SelectItem value="24h">24ч</SelectItem>
              </SelectContent>
            </Select>
          ) : undefined
        }
      >
        {historyLoading && serverPoints.length < 2 ? (
          <MonitoringChartEmpty>Загрузка истории...</MonitoringChartEmpty>
        ) : history.length < 2 ? (
          <MonitoringChartEmpty>Ожидание данных... (минимум 2 точки)</MonitoringChartEmpty>
        ) : (
          <ChartResponsive height={MONITORING_CHART_HEIGHT}>
            {({ width, height }) => (
              <LineChart width={width} height={height} data={history}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip {...monitoringChartTooltipProps} />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="ovpn"
                  name="OpenVPN"
                  stroke={MONITORING_PROTOCOL_COLORS.openvpn}
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="wg"
                  name="WireGuard"
                  stroke={MONITORING_PROTOCOL_COLORS.wireguard}
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="connections"
                  name="Всего"
                  stroke={MONITORING_PROTOCOL_COLORS.total}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            )}
          </ChartResponsive>
        )}
      </MonitoringChartCard>

      <MonitoringChartCard title="Активные подключения" description="По протоколу" icon={BarChart3}>
        <ChartResponsive height={MONITORING_CHART_HEIGHT}>
          {({ width, height }) => (
            <BarChart width={width} height={height} data={connectionsBar}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip {...monitoringChartTooltipProps} />
              <Bar dataKey="count" name="Клиенты" radius={[4, 4, 0, 0]}>
                {connectionsBar.map((entry) => (
                  <Cell key={entry.name} fill={getProtocolBarColor(entry.name)} />
                ))}
              </Bar>
            </BarChart>
          )}
        </ChartResponsive>
      </MonitoringChartCard>
    </div>
  )
}

export { formatBytes, totalTraffic }
