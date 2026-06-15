import { useCallback, useEffect, useMemo, useState } from 'react'
import { Columns3, Loader2 } from 'lucide-react'
import { ApiError, getNodesCompare } from '@/api/client'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import { NodeStatusBadge } from '@/components/NodeSelector'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import type { GlobalDashboardSummary, MonitoringNodeSummary, NodeStatus } from '@/types'

type CompareMetric = {
  key: string
  label: string
  format: (node: MonitoringNodeSummary) => string
}

function formatPercent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

const METRICS: CompareMetric[] = [
  { key: 'status', label: 'Статус', format: (n) => n.status },
  {
    key: 'vpn',
    label: 'Online OVPN / WG',
    format: (n) => `${n.connected_openvpn} / ${n.connected_wireguard}`,
  },
  {
    key: 'services',
    label: 'Службы active/total',
    format: (n) => `${n.active_services}/${n.total_services}`,
  },
  { key: 'cpu', label: 'CPU', format: (n) => formatPercent(n.cpu_percent) },
  { key: 'ram', label: 'RAM', format: (n) => formatPercent(n.memory_percent) },
  {
    key: 'traffic',
    label: 'Трафик (всего)',
    format: (n) => (n.total_traffic_bytes != null ? formatBytes(n.total_traffic_bytes) : '—'),
  },
  {
    key: 'cidr',
    label: 'CIDR маршруты',
    format: (n) => (n.cidr_routes_count != null ? String(n.cidr_routes_count) : '—'),
  },
]

export default function NodesCompareSection() {
  const { error: notifyError } = useNotifications()
  const [data, setData] = useState<GlobalDashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    setRefreshing(true)
    try {
      setData(await getNodesCompare())
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Ошибка загрузки сравнения узлов'
      notifyError(message)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [notifyError])

  useEffect(() => {
    void load()
  }, [load])

  const nodes = data?.nodes_summary ?? []
  const metricRows = useMemo(() => METRICS, [])

  if (loading && !data) {
    return (
      <Card>
        <CardContent>
          <Spinner label="Загрузка сравнения узлов..." className="py-6" />
        </CardContent>
      </Card>
    )
  }

  if (nodes.length < 2) return null

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Columns3 size={18} />
            Сравнение узлов
          </CardTitle>
          <CardDescription>Side-by-side метрики: online, CPU/RAM, трафик, CIDR</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={refreshing}>
          {refreshing ? <Loader2 size={14} className="animate-spin" /> : null}
          Обновить
        </Button>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-[160px]">Метрика</TableHead>
                {nodes.map((node) => (
                  <TableHead key={node.node_id} className="min-w-[140px] text-center">
                    <div className="flex flex-col items-center gap-1">
                      <span className="font-medium">{node.node_name}</span>
                      <NodeStatusBadge status={node.status as NodeStatus} showLabel={false} />
                    </div>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {metricRows.map((metric) => (
                <TableRow key={metric.key}>
                  <TableCell className="font-medium text-muted-foreground">{metric.label}</TableCell>
                  {nodes.map((node) => (
                    <TableCell key={`${metric.key}-${node.node_id}`} className="text-center">
                      {metric.key === 'status' ? (
                        <NodeStatusBadge status={node.status as NodeStatus} />
                      ) : metric.key === 'cpu' || metric.key === 'ram' ? (
                        <div className="mx-auto max-w-[120px] space-y-1">
                          {metric.key === 'cpu' && node.cpu_percent != null ? (
                            <Progress value={Math.min(100, node.cpu_percent)} className="h-2" />
                          ) : null}
                          {metric.key === 'ram' && node.memory_percent != null ? (
                            <Progress value={Math.min(100, node.memory_percent)} className="h-2" />
                          ) : null}
                          <span className="text-xs font-mono">{metric.format(node)}</span>
                        </div>
                      ) : (
                        <span className="font-mono text-xs">{metric.format(node)}</span>
                      )}
                      {node.error && metric.key === 'status' && (
                        <p className="mt-1 text-[10px] text-destructive">{node.error}</p>
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
