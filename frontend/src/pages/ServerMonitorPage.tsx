import { useEffect, useRef, useState } from 'react'
import { Activity, Cpu, HardDrive, MemoryStick, Network } from 'lucide-react'
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
import { ApiError, getBandwidthChart, getServerInterfaces, getServerMetrics } from '@/api/client'
import MetricCard from '@/components/noc/MetricCard'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import Spinner from '@/components/ui/Spinner'
import { NodeBadge } from '@/components/NodeSelector'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { BandwidthChart, ServerMetrics } from '@/types'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

export default function ServerMonitorPage() {
  const { user } = useAuth()
  const { activeNode } = useNode()
  const { error: notifyError } = useNotifications()
  const [metrics, setMetrics] = useState<ServerMetrics | null>(null)
  const [liveCpu, setLiveCpu] = useState<number | null>(null)
  const [liveRam, setLiveRam] = useState<number | null>(null)
  const [liveBw, setLiveBw] = useState<{ rx: number; tx: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [iface, setIface] = useState('eth0')
  const [ifaces, setIfaces] = useState<string[]>([])
  const [range, setRange] = useState<'1d' | '7d' | '30d'>('1d')
  const [bwChart, setBwChart] = useState<BandwidthChart | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (user?.role !== 'admin') return
    getServerInterfaces()
      .then((d) => {
        setIfaces(d.interfaces || [])
        if (d.interfaces?.[0]) setIface(d.interfaces[0])
      })
      .catch(() => {})
    getServerMetrics()
      .then(setMetrics)
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка метрик'))
      .finally(() => setLoading(false))
  }, [user?.role])

  useEffect(() => {
    if (user?.role !== 'admin' || !iface) return
    getBandwidthChart(iface, range)
      .then(setBwChart)
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка vnStat'))
  }, [user?.role, iface, range])

  useEffect(() => {
    if (user?.role !== 'admin') return
    const token = localStorage.getItem('token')
    if (!token) return
    const wsUrl = `${API_BASE.replace('/api', '')}/api/server-monitor/ws?token=${token}&iface=${encodeURIComponent(iface)}`.replace('http', 'ws')
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        setLiveCpu(data.cpu_percent)
        setLiveRam(data.memory_percent)
        if (data.bandwidth) {
          setLiveBw({ rx: data.bandwidth.rx_mbps_latest, tx: data.bandwidth.tx_mbps_latest })
        }
      } catch {
        /* ignore */
      }
    }
    return () => ws.close()
  }, [user?.role, iface])

  if (user?.role !== 'admin') {
    return <p className="text-muted-foreground">Мониторинг сервера доступен только администраторам.</p>
  }

  if (loading) return <Spinner label="Загрузка метрик сервера..." />

  const cpu = liveCpu ?? metrics?.cpu_percent ?? 0
  const ram = liveRam ?? metrics?.memory_percent ?? 0
  const chartData =
    bwChart?.labels?.map((label, i) => ({
      label,
      rx: bwChart.rx_mbps[i] ?? 0,
      tx: bwChart.tx_mbps[i] ?? 0,
    })) ?? []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Мониторинг сервера</h2>
          <p className="text-sm text-muted-foreground">
            CPU, RAM, vnStat bandwidth — WebSocket каждые 2с
            {metrics?.hostname ? ` · ${metrics.hostname}` : ''}
          </p>
        </div>
        <NodeBadge name={activeNode?.name ?? metrics?.node_name} status={activeNode?.status} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="CPU" value={`${cpu}%`} icon={Cpu} accent={cpu > 80 ? 'red' : 'cyan'} />
        <MetricCard label="RAM" value={`${ram}%`} icon={MemoryStick} accent={ram > 80 ? 'red' : 'green'} />
        <MetricCard
          label="RX (live)"
          value={liveBw ? `${liveBw.rx} Mbps` : '—'}
          icon={Network}
          accent="cyan"
        />
        <MetricCard
          label="TX (live)"
          value={liveBw ? `${liveBw.tx} Mbps` : '—'}
          icon={Activity}
          accent="amber"
        />
        <MetricCard label="Uptime" value={metrics?.uptime || '—'} icon={HardDrive} />
      </div>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">Трафик (vnStat)</CardTitle>
            <CardDescription>Интерфейс: {iface}</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              className="rounded-md border bg-background px-2 py-1 text-sm"
              value={iface}
              onChange={(e) => setIface(e.target.value)}
            >
              {(ifaces.length ? ifaces : [iface]).map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
            {(['1d', '7d', '30d'] as const).map((r) => (
              <Button key={r} size="sm" variant={range === r ? 'default' : 'outline'} onClick={() => setRange(r)}>
                {r}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {bwChart?.error ? (
            <p className="text-sm text-muted-foreground">{bwChart.error}</p>
          ) : chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} unit=" Mbps" />
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="rx" name="RX" stroke="#22d3ee" fill="#22d3ee33" />
                <Area type="monotone" dataKey="tx" name="TX" stroke="#f59e0b" fill="#f59e0b33" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground">Нет данных vnStat для выбранного интерфейса</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Система</CardTitle>
          <CardDescription>Load average и ресурсы</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm md:grid-cols-3">
          <div>Load 1m: {metrics?.load_average?.load_1m ?? '—'}</div>
          <div>Load 5m: {metrics?.load_average?.load_5m ?? '—'}</div>
          <div>Load 15m: {metrics?.load_average?.load_15m ?? '—'}</div>
          <div>RAM: {metrics ? `${Math.round(metrics.memory_used / 1e9)} / ${Math.round(metrics.memory_total / 1e9)} GB` : '—'}</div>
          <div>Диск: {metrics?.disk_percent ?? 0}%</div>
        </CardContent>
      </Card>
    </div>
  )
}
