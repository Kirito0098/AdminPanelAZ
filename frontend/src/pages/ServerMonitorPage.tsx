import { useEffect, useRef, useState } from 'react'
import { Cpu, HardDrive, MemoryStick } from 'lucide-react'
import { ApiError, getServerMetrics } from '@/api/client'
import MetricCard from '@/components/noc/MetricCard'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Spinner from '@/components/ui/Spinner'
import { useAuth } from '@/context/AuthContext'
import { useNotifications } from '@/context/NotificationContext'
import type { ServerMetrics } from '@/types'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

export default function ServerMonitorPage() {
  const { user } = useAuth()
  const { error: notifyError } = useNotifications()
  const [metrics, setMetrics] = useState<ServerMetrics | null>(null)
  const [liveCpu, setLiveCpu] = useState<number | null>(null)
  const [liveRam, setLiveRam] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (user?.role !== 'admin') return
    getServerMetrics()
      .then(setMetrics)
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка метрик'))
      .finally(() => setLoading(false))
  }, [user?.role])

  useEffect(() => {
    if (user?.role !== 'admin') return
    const token = localStorage.getItem('token')
    if (!token) return
    const wsUrl = `${API_BASE.replace('/api', '')}/api/server-monitor/ws?token=${token}`.replace('http', 'ws')
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        setLiveCpu(data.cpu_percent)
        setLiveRam(data.memory_percent)
      } catch {
        /* ignore */
      }
    }
    return () => ws.close()
  }, [user?.role])

  if (user?.role !== 'admin') {
    return <p className="text-muted-foreground">Мониторинг сервера доступен только администраторам.</p>
  }

  if (loading) return <Spinner label="Загрузка метрик сервера..." />

  const cpu = liveCpu ?? metrics?.cpu_percent ?? 0
  const ram = liveRam ?? metrics?.memory_percent ?? 0

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Мониторинг сервера</h2>
        <p className="text-sm text-muted-foreground">CPU, RAM, диск — WebSocket обновление каждые 2с</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="CPU" value={`${cpu}%`} icon={Cpu} accent={cpu > 80 ? 'red' : 'cyan'} />
        <MetricCard label="RAM" value={`${ram}%`} icon={MemoryStick} accent={ram > 80 ? 'red' : 'green'} />
        <MetricCard
          label="Диск"
          value={`${metrics?.disk_percent ?? 0}%`}
          sub={metrics ? `${Math.round(metrics.disk_percent)}% занято` : undefined}
          icon={HardDrive}
          accent="amber"
        />
        <MetricCard label="Uptime" value={metrics?.uptime || '—'} icon={Cpu} />
      </div>
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
        </CardContent>
      </Card>
    </div>
  )
}
