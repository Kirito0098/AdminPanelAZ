import { useCallback, useEffect, useState } from 'react'
import { Activity, Cpu, LayoutGrid, Loader2, Server, Wifi } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, getGlobalDashboardSummary } from '@/api/client'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import NodesCompareSection from '@/components/dashboard/NodesCompareSection'
import MetricCard from '@/components/noc/MetricCard'
import { NodeStatusBadge } from '@/components/NodeSelector'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Progress } from '@/components/ui/progress'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useNotifications } from '@/context/NotificationContext'
import { formatDateTime } from '@/lib/datetime'
import type { GlobalDashboardSummary, NodeStatus } from '@/types'

const REFRESH_INTERVAL_MS = 45_000

function formatPercent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

function MetricProgress({ value }: { value: number }) {
  const clamped = Math.min(100, Math.max(0, value))
  return <Progress value={clamped} className="h-2" />
}

export default function GlobalDashboardSection() {
  const { error: notifyError } = useNotifications()
  const [data, setData] = useState<GlobalDashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async (opts: { initial?: boolean } = {}) => {
    const { initial = false } = opts
    if (initial) setLoading(true)
    else setRefreshing(true)
    try {
      setData(await getGlobalDashboardSummary())
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Ошибка загрузки обзора узлов'
      notifyError(message)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [notifyError])

  useEffect(() => {
    void load({ initial: true })
  }, [load])

  useEffect(() => {
    const interval = window.setInterval(() => {
      void load()
    }, REFRESH_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [load])

  if (loading && !data) {
    return (
      <Card>
        <CardContent>
          <Spinner label="Загрузка обзора всех узлов..." className="py-6" />
        </CardContent>
      </Card>
    )
  }

  if (!data) return null

  const totalOnline = (data.total_connected_openvpn ?? 0) + (data.total_connected_wireguard ?? 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <LayoutGrid size={20} />
          </div>
          <div>
            <h3 className="text-lg font-semibold tracking-tight">Обзор всех узлов</h3>
            <p className="text-sm text-muted-foreground">
              Сводка VPN-подключений и ресурсов без переключения активного узла
              {data.timestamp && (
                <> · обновлено {formatDateTime(data.timestamp)}</>
              )}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={refreshing}>
            {refreshing ? <Loader2 size={14} className="animate-spin" /> : <Activity size={14} />}
            Обновить
          </Button>
          <Button variant="secondary" size="sm" asChild>
            <Link to="/monitoring">NOC Мониторинг</Link>
          </Button>
        </div>
      </div>

      <SettingsAlert variant="info" title="Global dashboard">
        Данные собираются одним запросом на backend с кэшем ~45 с. Управление клиентами ниже по-прежнему
        привязано к <strong>активному узлу</strong>.
      </SettingsAlert>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Узлы online"
          value={`${data.nodes_online ?? 0}/${data.nodes_total ?? 0}`}
          sub="доступность по health"
          icon={Server}
          accent="cyan"
        />
        <MetricCard
          label="Подключено VPN"
          value={String(totalOnline)}
          sub={`OVPN ${data.total_connected_openvpn ?? 0} · WG ${data.total_connected_wireguard ?? 0}`}
          icon={Wifi}
          accent="green"
        />
        <MetricCard
          label="OpenVPN"
          value={String(data.total_connected_openvpn ?? 0)}
          sub="активных сессий"
          icon={Activity}
          accent="amber"
        />
        <MetricCard
          label="WireGuard"
          value={String(data.total_connected_wireguard ?? 0)}
          sub="с handshake"
          icon={Wifi}
          accent="default"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Server size={18} />
            Узлы
          </CardTitle>
          <CardDescription>Health, подключения, CPU/RAM, трафик и CIDR</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Узел</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead className="text-right">OVPN</TableHead>
                  <TableHead className="text-right">WG</TableHead>
                  <TableHead className="text-right">Службы</TableHead>
                  <TableHead>CPU</TableHead>
                  <TableHead>RAM</TableHead>
                  <TableHead className="text-right">Трафик</TableHead>
                  <TableHead className="text-right">CIDR</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.nodes_summary.map((node) => (
                  <TableRow key={node.node_id}>
                    <TableCell className="font-medium">{node.node_name}</TableCell>
                    <TableCell>
                      <NodeStatusBadge status={node.status as NodeStatus} />
                      {node.error && (
                        <p className="mt-1 max-w-xs text-[11px] text-destructive">{node.error}</p>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">{node.connected_openvpn}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{node.connected_wireguard}</TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {node.active_services}/{node.total_services}
                    </TableCell>
                    <TableCell className="min-w-[120px]">
                      {node.cpu_percent != null ? (
                        <div className="space-y-1">
                          <MetricProgress value={node.cpu_percent} />
                          <span className="text-[10px] text-muted-foreground">{formatPercent(node.cpu_percent)}</span>
                        </div>
                      ) : (
                        <Badge variant="outline" className="text-[10px]">
                          <Cpu size={10} className="mr-1" />
                          н/д
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="min-w-[120px]">
                      {node.memory_percent != null ? (
                        <div className="space-y-1">
                          <MetricProgress value={node.memory_percent} />
                          <span className="text-[10px] text-muted-foreground">
                            {formatPercent(node.memory_percent)}
                          </span>
                        </div>
                      ) : (
                        <Badge variant="outline" className="text-[10px]">н/д</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {node.total_traffic_bytes != null ? formatBytes(node.total_traffic_bytes) : '—'}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {node.cidr_routes_count ?? '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <NodesCompareSection />
    </div>
  )
}
