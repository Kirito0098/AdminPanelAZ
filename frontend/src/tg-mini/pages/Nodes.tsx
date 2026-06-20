import { useCallback, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { statusLabels } from '@/components/NodeSelector'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import Spinner from '@/components/ui/Spinner'
import { formatDateTime } from '@/lib/datetime'
import { LABEL_LAST_SEEN } from '@/lib/uiLabels'
import {
  activateTgNode,
  checkTgNodeHealth,
  getTgNodes,
} from '@/tg-mini/api'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import type { NodeStatus, TgMiniNode } from '@/types'

const statusTone: Record<NodeStatus, string> = {
  online: 'text-emerald-600',
  offline: 'text-red-600',
  unknown: 'text-amber-600',
}

function getNodeMeta(node: TgMiniNode) {
  const meta = node.metadata ?? {}
  return {
    serverIp: typeof meta.server_ip === 'string' ? meta.server_ip : null,
    servicesLabel:
      typeof meta.services_active === 'number' && typeof meta.services_total === 'number'
        ? `${meta.services_active}/${meta.services_total}`
        : null,
    agentVersion: typeof meta.agent_version === 'string' ? meta.agent_version : null,
    lastError: typeof meta.last_error === 'string' ? meta.last_error : null,
  }
}

function formatLastSeen(value?: string | null) {
  if (!value) return '—'
  return formatDateTime(value)
}

export default function Nodes() {
  const { isAdmin } = useTgAuth()
  const [nodes, setNodes] = useState<TgMiniNode[]>([])
  const [activeNodeId, setActiveNodeId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTgNodes()
      setNodes(data.nodes)
      setActiveNodeId(data.active_node_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!isAdmin) return
    void load()
  }, [isAdmin, load])

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  const replaceNode = (updated: TgMiniNode) => {
    setNodes((current) => current.map((node) => (node.id === updated.id ? updated : node)))
    if (updated.is_active) {
      setActiveNodeId(updated.id)
      setNodes((current) =>
        current.map((node) => ({
          ...node,
          is_active: node.id === updated.id,
        })),
      )
    }
  }

  const handleHealth = async (nodeId: number) => {
    setBusyId(nodeId)
    setError(null)
    try {
      const result = await checkTgNodeHealth(nodeId)
      replaceNode(result.node)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка проверки')
    } finally {
      setBusyId(null)
    }
  }

  const handleActivate = async (nodeId: number) => {
    setBusyId(nodeId)
    setError(null)
    try {
      const result = await activateTgNode(nodeId)
      replaceNode(result.node)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка активации')
    } finally {
      setBusyId(null)
    }
  }

  if (loading) {
    return (
      <div className="tg-mini-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">VPN-узлы</h2>
          <p className="text-xs text-muted-foreground">Просмотр, проверка связи и переключение активного узла</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
          Обновить
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {nodes.length === 0 ? (
        <Card>
          <CardContent className="p-4 text-sm text-muted-foreground">
            Узлы не найдены. Добавьте VPN-узел в веб-панели.
          </CardContent>
        </Card>
      ) : (
        nodes.map((node) => {
          const meta = getNodeMeta(node)
          const isActive = node.id === activeNodeId || node.is_active
          const busy = busyId === node.id
          return (
            <Card key={node.id} className={isActive ? 'border-primary/40' : undefined}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-base leading-tight">
                    {node.name}
                    {isActive && (
                      <Badge variant="default" className="ml-2 align-middle">
                        активный
                      </Badge>
                    )}
                  </CardTitle>
                  <span className={`text-xs font-medium ${statusTone[node.status]}`}>
                    {statusLabels[node.status]}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="space-y-1 text-muted-foreground">
                  <p>
                    <span className="text-foreground">{node.host}:{node.port}</span>
                    {node.is_local ? ' · локальный' : node.mtls_enabled ? ' · mTLS' : ' · HTTP'}
                  </p>
                  {meta.serverIp && <p>IP сервера: {meta.serverIp}</p>}
                  {meta.servicesLabel && <p>Службы: {meta.servicesLabel}</p>}
                  {meta.agentVersion && <p>Агент узла: {meta.agentVersion}</p>}
                  <p className="text-xs">{LABEL_LAST_SEEN}: {formatLastSeen(node.last_seen_at)}</p>
                  {meta.lastError && <p className="text-xs text-destructive">{meta.lastError}</p>}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => void handleHealth(node.id)}
                  >
                    {busy ? '...' : 'Проверить'}
                  </Button>
                  {!isActive && (
                    <Button
                      type="button"
                      size="sm"
                      disabled={busy}
                      onClick={() => void handleActivate(node.id)}
                    >
                      Сделать активным
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )
        })
      )}
    </div>
  )
}
