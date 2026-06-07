import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { MonitoringOverview } from '@/types'

const CHART_COLORS = ['hsl(187, 72%, 45%)', 'hsl(142, 71%, 45%)', 'hsl(38, 92%, 50%)', 'hsl(0, 84%, 60%)', 'hsl(217, 33%, 45%)']
const MAX_HISTORY = 20

interface HistoryPoint {
  time: string
  connections: number
  ovpn: number
  wg: number
  trafficMb: number
}

interface MonitoringChartsProps {
  data: MonitoringOverview
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

function totalTraffic(data: MonitoringOverview) {
  const ovpn = data.openvpn_clients.reduce((s, c) => s + c.bytes_received + c.bytes_sent, 0)
  const wg = data.wireguard_peers.reduce((s, p) => s + p.transfer_rx + p.transfer_tx, 0)
  return ovpn + wg
}

export default function MonitoringCharts({ data }: MonitoringChartsProps) {
  const historyRef = useRef<HistoryPoint[]>([])
  const [, bump] = useState(0)

  useEffect(() => {
    const wgActive = data.wireguard_peers.filter((p) => p.latest_handshake).length
    const point: HistoryPoint = {
      time: new Date(data.timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      connections: data.openvpn_clients.length + wgActive,
      ovpn: data.openvpn_clients.length,
      wg: wgActive,
      trafficMb: Math.round(totalTraffic(data) / (1024 * 1024)),
    }
    const last = historyRef.current[historyRef.current.length - 1]
    if (!last || last.time !== point.time) {
      historyRef.current = [...historyRef.current.slice(-(MAX_HISTORY - 1)), point]
      bump((n) => n + 1)
    }
  }, [data])

  const history = historyRef.current

  const servicePie = useMemo(() => {
    const active = data.services.filter((s) => s.active).length
    const inactive = data.services.length - active
    return [
      { name: 'Online', value: active },
      { name: 'Offline', value: inactive },
    ].filter((d) => d.value > 0)
  }, [data.services])

  const connectionsBar = useMemo(() => {
    const wgActive = data.wireguard_peers.filter((p) => p.latest_handshake).length
    return [
      { name: 'OpenVPN', count: data.openvpn_clients.length },
      { name: 'WireGuard', count: wgActive },
    ]
  }, [data])

  const trafficBar = useMemo(() => {
    const items: { name: string; rx: number; tx: number }[] = []
    data.openvpn_clients.forEach((c) => {
      items.push({ name: c.common_name.slice(0, 12), rx: c.bytes_received, tx: c.bytes_sent })
    })
    data.wireguard_peers
      .filter((p) => p.latest_handshake)
      .forEach((p) => {
        items.push({
          name: (p.client_name || p.interface).slice(0, 12),
          rx: p.transfer_rx,
          tx: p.transfer_tx,
        })
      })
    return items.slice(0, 8)
  }, [data])

  const chartTooltipStyle = {
    backgroundColor: 'hsl(var(--popover))',
    border: '1px solid hsl(var(--border))',
    borderRadius: '8px',
    color: 'hsl(var(--popover-foreground))',
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Подключения во времени</CardTitle>
          <CardDescription>История автообновления (до {MAX_HISTORY} точек)</CardDescription>
        </CardHeader>
        <CardContent>
          {history.length < 2 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Ожидание данных... (минимум 2 обновления)
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={history}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={chartTooltipStyle} />
                <Legend />
                <Line type="monotone" dataKey="connections" name="Всего" stroke={CHART_COLORS[0]} strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="ovpn" name="OpenVPN" stroke={CHART_COLORS[1]} strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="wg" name="WireGuard" stroke={CHART_COLORS[2]} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Статус служб</CardTitle>
          <CardDescription>Online vs offline</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={servicePie}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={4}
                dataKey="value"
                label={({ name, value }) => `${name}: ${value}`}
              >
                {servicePie.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? CHART_COLORS[1] : CHART_COLORS[3]} />
                ))}
              </Pie>
              <Tooltip contentStyle={chartTooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Активные подключения</CardTitle>
          <CardDescription>По протоколу</CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={connectionsBar}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={chartTooltipStyle} />
              <Bar dataKey="count" name="Клиенты" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Трафик сессий</CardTitle>
          <CardDescription>RX / TX по клиентам (MB)</CardDescription>
        </CardHeader>
        <CardContent>
          {trafficBar.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Нет активных сессий с трафиком</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={trafficBar.map((t) => ({ ...t, rx: t.rx / (1024 * 1024), tx: t.tx / (1024 * 1024) }))}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={chartTooltipStyle}
                  formatter={(value: number, name: string) => [`${value.toFixed(2)} MB`, name === 'rx' ? 'RX' : 'TX']}
                />
                <Legend formatter={(v) => (v === 'rx' ? 'RX' : 'TX')} />
                <Bar dataKey="rx" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                <Bar dataKey="tx" fill={CHART_COLORS[1]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export { formatBytes, totalTraffic }
