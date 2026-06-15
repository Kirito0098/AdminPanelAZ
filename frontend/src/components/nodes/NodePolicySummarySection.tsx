import { useCallback, useEffect, useState } from 'react'
import { Loader2, Shield } from 'lucide-react'
import { ApiError, getNodePolicySummary } from '@/api/client'
import { NodeStatusBadge } from '@/components/NodeSelector'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useNotifications } from '@/context/NotificationContext'
import type { NodePolicySummary, NodeStatus } from '@/types'

type NodePolicySummarySectionProps = {
  nodes: Array<{ id: number; name: string; status: string }>
}

export default function NodePolicySummarySection({ nodes }: NodePolicySummarySectionProps) {
  const { error: notifyError } = useNotifications()
  const [rows, setRows] = useState<NodePolicySummary[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    setRefreshing(true)
    try {
      setRows(await getNodePolicySummary())
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки политик узлов')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [notifyError])

  useEffect(() => {
    if (nodes.length === 0) {
      setLoading(false)
      return
    }
    void load()
  }, [load, nodes.length])

  if (nodes.length < 2) return null

  if (loading && rows.length === 0) {
    return (
      <Card>
        <CardContent>
          <Spinner label="Загрузка политик per-node..." className="py-6" />
        </CardContent>
      </Card>
    )
  }

  const statusById = Object.fromEntries(nodes.map((n) => [n.id, n.status]))

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield size={18} />
            Политики per-node
          </CardTitle>
          <CardDescription>
            Лимиты и блокировки OpenVPN/WireGuard изолированы по node_id (EU vs RU и т.д.)
          </CardDescription>
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
                <TableHead>Узел</TableHead>
                <TableHead className="text-right">OVPN</TableHead>
                <TableHead className="text-right">WG</TableHead>
                <TableHead className="text-right">Заблок.</TableHead>
                <TableHead className="text-right">Лимиты</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.node_id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{row.node_name}</span>
                      <NodeStatusBadge status={(statusById[row.node_id] ?? 'unknown') as NodeStatus} showLabel={false} />
                    </div>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">{row.openvpn_policies}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{row.wireguard_policies}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{row.blocked_clients}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{row.traffic_limited_clients}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
