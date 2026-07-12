import { useCallback, useEffect, useState } from 'react'
import { Loader2, Pencil, Shield } from 'lucide-react'
import { ApiError, getNodePolicySummary } from '@/api/client'
import { NodeStatusBadge } from '@/components/NodeSelector'
import NodeDefaultPolicyWizard, { formatRouteMode } from '@/components/nodes/NodeDefaultPolicyWizard'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
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
import type { NodeClientPolicyHint, NodePolicySummary, NodeStatus } from '@/types'

type NodePolicySummarySectionProps = {
  nodes: Array<{ id: number; name: string; status: string }>
}

function defaultLimitsLabel(row: NodePolicySummary): string {
  const parts: string[] = []
  if (row.default_openvpn_limit_human) {
    parts.push(`OVPN ${row.default_openvpn_limit_human}`)
  }
  if (row.default_wireguard_limit_human) {
    parts.push(`WG ${row.default_wireguard_limit_human}`)
  }
  if (parts.length === 0) return '—'
  return parts.join(' · ')
}

function formatClientHint(hint: NodeClientPolicyHint): string {
  const protocol = hint.protocol === 'wireguard' ? 'WG' : 'OVPN'
  const parts = [hint.client_name, protocol]
  if (hint.limit_human) parts.push(`лимит ${hint.limit_human}`)
  if (hint.is_blocked) parts.push('заблок.')
  return parts.join(', ')
}

function NodePolicySummaryCard({
  row,
  status,
  onEdit,
}: {
  row: NodePolicySummary
  status: string
  onEdit: () => void
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{row.node_name}</span>
            <NodeStatusBadge status={status as NodeStatus} showLabel={false} />
          </div>
          {(row.client_hints?.length ?? 0) > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">
              {row.client_hints!.map(formatClientHint).join(' · ')}
            </p>
          ) : null}
        </div>
        <Button variant="ghost" size="sm" className="h-8 shrink-0 px-2" onClick={onEdit}>
          <Pencil size={14} />
          <span className="sr-only">Редактировать</span>
        </Button>
      </div>
      <dl className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Дефолтные лимиты</dt>
          <dd className="mt-0.5 font-mono">{defaultLimitsLabel(row)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Маршрут</dt>
          <dd className="mt-0.5">{formatRouteMode(row.default_route_mode)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">OVPN / WG</dt>
          <dd className="mt-0.5 font-mono">
            {row.openvpn_policies} / {row.wireguard_policies}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Заблок. / лимиты</dt>
          <dd className="mt-0.5 font-mono">
            {row.blocked_clients} / {row.traffic_limited_clients}
          </dd>
        </div>
      </dl>
    </Card>
  )
}

export default function NodePolicySummarySection({ nodes }: NodePolicySummarySectionProps) {
  const { error: notifyError } = useNotifications()
  const [rows, setRows] = useState<NodePolicySummary[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [editNodeId, setEditNodeId] = useState<number | null>(null)
  const [editNodeName, setEditNodeName] = useState('')

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

  const openEdit = (nodeId: number, nodeName: string) => {
    setEditNodeId(nodeId)
    setEditNodeName(nodeName)
  }

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
    <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield size={18} />
              Политики per-node
            </CardTitle>
            <CardDescription>
              Дефолтные лимиты и маршруты для новых клиентов. Счётчики OVPN/WG/Лимиты — политики
              уже созданных клиентов (редактируются в карточке клиента).
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={refreshing}>
            {refreshing ? <Loader2 size={14} className="animate-spin" /> : null}
            Обновить
          </Button>
        </CardHeader>
        <CardContent>
          <ResponsiveDataView
            mobile={rows.map((row) => (
              <NodePolicySummaryCard
                key={row.node_id}
                row={row}
                status={statusById[row.node_id] ?? 'unknown'}
                onEdit={() => openEdit(row.node_id, row.node_name)}
              />
            ))}
            desktop={
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Узел</TableHead>
                    <TableHead>Дефолтные лимиты</TableHead>
                    <TableHead>Маршрут</TableHead>
                    <TableHead className="text-right">OVPN</TableHead>
                    <TableHead className="text-right">WG</TableHead>
                    <TableHead className="text-right">Заблок.</TableHead>
                    <TableHead className="text-right">Лимиты</TableHead>
                    <TableHead className="w-[90px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.node_id}>
                      <TableCell>
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{row.node_name}</span>
                            <NodeStatusBadge
                              status={(statusById[row.node_id] ?? 'unknown') as NodeStatus}
                              showLabel={false}
                            />
                          </div>
                          {(row.client_hints?.length ?? 0) > 0 ? (
                            <p className="text-xs text-muted-foreground">
                              {row.client_hints!.map(formatClientHint).join(' · ')}
                            </p>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{defaultLimitsLabel(row)}</TableCell>
                      <TableCell className="text-xs">{formatRouteMode(row.default_route_mode)}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{row.openvpn_policies}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{row.wireguard_policies}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{row.blocked_clients}</TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {row.traffic_limited_clients}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 px-2"
                          onClick={() => openEdit(row.node_id, row.node_name)}
                        >
                          <Pencil size={14} />
                          <span className="sr-only">Редактировать</span>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            }
            mobileClassName="space-y-3"
            desktopClassName="overflow-x-auto rounded-md border"
          />
        </CardContent>
      </Card>

      <NodeDefaultPolicyWizard
        open={editNodeId != null}
        onOpenChange={(open) => {
          if (!open) {
            setEditNodeId(null)
            setEditNodeName('')
          }
        }}
        nodeId={editNodeId}
        nodeName={editNodeName}
        onSaved={() => void load()}
      />
    </>
  )
}
