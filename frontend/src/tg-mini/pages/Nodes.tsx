import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  Check,
  Copy,
  Globe,
  Loader2,
  Search,
  Server,
  ShieldCheck,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { Navigate } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { NodeStatusBadge } from '@/components/NodeSelector'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import MetricCard from '@/components/noc/MetricCard'
import { formatDateTime } from '@/lib/datetime'
import { LABEL_LAST_SEEN, NODE_STATUS_LABELS } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import MiniListToolbar, { matchesSearchQuery } from '@/tg-mini/components/MiniListToolbar'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import { activateTgNode, checkTgNodeHealth, getTgNodes } from '@/tg-mini/api'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import type { NodeStatus, TgMiniNode } from '@/types'

type StatusFilter = 'all' | NodeStatus

const STATUS_FILTERS: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'Все' },
  { value: 'online', label: 'В сети' },
  { value: 'offline', label: 'Не в сети' },
  { value: 'unknown', label: '?' },
]

function NodesSkeleton() {
  return (
    <div className="tg-mini-dashboard space-y-4" aria-busy="true" aria-label="Загрузка узлов">
      <div className="tg-mini-skeleton" style={{ height: '2.5rem' }} />
      <div className="tg-mini-cards">
        <div className="tg-mini-skeleton tg-mini-skeleton-card" />
        <div className="tg-mini-skeleton tg-mini-skeleton-card" />
      </div>
      <div className="tg-mini-skeleton" style={{ height: '2.75rem' }} />
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="tg-mini-skeleton tg-mini-skeleton-section" />
      ))}
    </div>
  )
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

function nodeAddress(node: TgMiniNode) {
  return node.is_local ? 'локальный' : `${node.host}:${node.port}`
}

function MiniCopyValue({ value, label }: { value: string; label: string }) {
  const [hint, setHint] = useState<string | null>(null)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setHint('Скопировано')
      window.setTimeout(() => setHint(null), 1600)
    } catch {
      setHint('Ошибка')
      window.setTimeout(() => setHint(null), 1600)
    }
  }

  return (
    <button
      type="button"
      className="tg-mini-copy-ip tg-mini-copy-ip--inline"
      onClick={() => void copy()}
      title={`Скопировать ${label}`}
    >
      <span className="mono truncate">{value}</span>
      <Copy size={13} className="shrink-0 opacity-60" aria-hidden />
      {hint && <span className="tg-mini-copy-hint">{hint}</span>}
    </button>
  )
}

function NodeTransportBadge({ node }: { node: TgMiniNode }) {
  if (node.is_local) {
    return (
      <Badge variant="secondary" className="text-[10px] font-normal">
        Локальный
      </Badge>
    )
  }
  return (
    <>
      <Badge variant="outline" className="gap-1 text-[10px] font-normal">
        <Globe size={10} aria-hidden />
        Удалённый
      </Badge>
      <Badge variant={node.mtls_enabled ? 'default' : 'outline'} className="text-[10px] font-normal">
        {node.mtls_enabled ? 'mTLS' : 'HTTP'}
      </Badge>
    </>
  )
}

type BusyAction = { id: number; kind: 'health' | 'activate' }

interface MiniNodeCardProps {
  node: TgMiniNode
  isActive: boolean
  busy: BusyAction | null
  flash?: string | null
  onHealth: () => void
  onActivate: () => void
}

function MiniNodeCard({ node, isActive, busy, flash, onHealth, onActivate }: MiniNodeCardProps) {
  const meta = getNodeMeta(node)
  const isBusy = busy?.id === node.id
  const healthBusy = isBusy && busy?.kind === 'health'
  const activateBusy = isBusy && busy?.kind === 'activate'

  return (
    <Card
      className={cn(
        'tg-mini-node-card',
        isActive && 'tg-mini-node-card--active',
        node.status === 'offline' && 'tg-mini-node-card--offline',
      )}
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Server size={16} className="shrink-0 text-muted-foreground" aria-hidden />
              <h3 className="truncate text-sm font-semibold leading-tight">{node.name}</h3>
              {isActive && (
                <Badge variant="default" className="gap-1 text-[10px] font-normal">
                  <Check size={10} aria-hidden />
                  активный
                </Badge>
              )}
            </div>
            <p className="mono text-xs text-muted-foreground">{nodeAddress(node)}</p>
          </div>
          <NodeStatusBadge status={node.status} />
        </div>

        <div className="tg-mini-node-meta-grid">
          <div>
            <p className="tg-mini-node-meta-label">IP сервера</p>
            {meta.serverIp ? (
              <MiniCopyValue value={meta.serverIp} label="IP сервера" />
            ) : (
              <p className="text-xs text-muted-foreground">—</p>
            )}
          </div>
          <div>
            <p className="tg-mini-node-meta-label">Службы</p>
            <p className="text-xs font-medium tabular-nums">{meta.servicesLabel ?? '—'}</p>
          </div>
          <div className="tg-mini-node-meta-span">
            <p className="tg-mini-node-meta-label">Агент</p>
            <p className="mono text-xs">{meta.agentVersion ?? '—'}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <NodeTransportBadge node={node} />
          <span className="text-[11px] text-muted-foreground">
            {LABEL_LAST_SEEN}: {formatLastSeen(node.last_seen_at)}
          </span>
        </div>

        {node.status === 'offline' && meta.lastError && (
          <p className="rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-2 text-xs leading-snug text-destructive">
            {meta.lastError}
          </p>
        )}

        {flash && <p className="text-xs font-medium text-emerald-600 dark:text-emerald-400">{flash}</p>}

        <div className="flex flex-wrap gap-2 pt-0.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5"
            disabled={isBusy}
            onClick={onHealth}
          >
            {healthBusy ? (
              <Loader2 size={14} className="animate-spin" aria-hidden />
            ) : (
              <Activity size={14} aria-hidden />
            )}
            Проверить
          </Button>
          {!isActive && (
            <Button type="button" size="sm" className="gap-1.5" disabled={isBusy} onClick={onActivate}>
              {activateBusy ? (
                <Loader2 size={14} className="animate-spin" aria-hidden />
              ) : (
                <ShieldCheck size={14} aria-hidden />
              )}
              Сделать активным
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export default function Nodes() {
  const { isAdmin } = useTgAuth()
  const [nodes, setNodes] = useState<TgMiniNode[]>([])
  const [activeNodeId, setActiveNodeId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [busy, setBusy] = useState<BusyAction | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [flashByNode, setFlashByNode] = useState<Record<number, string>>({})

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)
    try {
      const data = await getTgNodes()
      setNodes(data.nodes)
      setActiveNodeId(data.active_node_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    if (!isAdmin) return
    void load()
  }, [isAdmin, load])

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  const activeNode = useMemo(
    () => nodes.find((node) => node.id === activeNodeId || node.is_active) ?? null,
    [nodes, activeNodeId],
  )

  const onlineCount = useMemo(() => nodes.filter((node) => node.status === 'online').length, [nodes])

  const statusCounts = useMemo(
    () => ({
      all: nodes.length,
      online: nodes.filter((node) => node.status === 'online').length,
      offline: nodes.filter((node) => node.status === 'offline').length,
      unknown: nodes.filter((node) => node.status === 'unknown').length,
    }),
    [nodes],
  )

  const sortedNodes = useMemo(() => {
    return [...nodes].sort((a, b) => {
      const aActive = a.id === activeNodeId || a.is_active
      const bActive = b.id === activeNodeId || b.is_active
      if (aActive !== bActive) return aActive ? -1 : 1
      if (a.status !== b.status) {
        const order: Record<NodeStatus, number> = { online: 0, unknown: 1, offline: 2 }
        return order[a.status] - order[b.status]
      }
      return a.name.localeCompare(b.name, 'ru')
    })
  }, [nodes, activeNodeId])

  const filteredNodes = useMemo(() => {
    return sortedNodes.filter((node) => {
      if (statusFilter !== 'all' && node.status !== statusFilter) return false
      const meta = getNodeMeta(node)
      return (
        matchesSearchQuery(node.name, search) ||
        matchesSearchQuery(node.host, search) ||
        matchesSearchQuery(meta.serverIp || '', search)
      )
    })
  }, [sortedNodes, statusFilter, search])

  const hasActiveFilters = search.trim().length > 0 || statusFilter !== 'all'

  const resetFilters = () => {
    setSearch('')
    setStatusFilter('all')
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

  const showFlash = (nodeId: number, text: string) => {
    setFlashByNode((current) => ({ ...current, [nodeId]: text }))
    window.setTimeout(() => {
      setFlashByNode((current) => {
        const next = { ...current }
        delete next[nodeId]
        return next
      })
    }, 2400)
  }

  const handleHealth = async (nodeId: number) => {
    setBusy({ id: nodeId, kind: 'health' })
    setError(null)
    try {
      const result = await checkTgNodeHealth(nodeId)
      replaceNode(result.node)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      showFlash(nodeId, `Статус: ${NODE_STATUS_LABELS[result.node.status]}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка проверки')
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('error')
    } finally {
      setBusy(null)
    }
  }

  const handleActivate = async (nodeId: number) => {
    setBusy({ id: nodeId, kind: 'activate' })
    setError(null)
    try {
      const result = await activateTgNode(nodeId)
      replaceNode(result.node)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      showFlash(nodeId, 'Узел активирован')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка активации')
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('error')
    } finally {
      setBusy(null)
    }
  }

  if (loading) {
    return <NodesSkeleton />
  }

  return (
    <div className="tg-mini-dashboard space-y-4">
      <MiniPageHeader
        title="VPN-узлы"
        subtitle="Проверка связи и переключение активного узла"
        onRefresh={() => void load({ silent: true })}
        refreshing={refreshing}
      />

      {error && (
        <div className="tg-mini-inline-alert" role="alert">
          {error}
        </div>
      )}

      {nodes.length > 0 && (
        <>
          <div className="tg-mini-cards">
            <MetricCard
              label="В сети"
              value={String(onlineCount)}
              sub={`из ${nodes.length} узлов`}
              icon={onlineCount === nodes.length ? Wifi : WifiOff}
              accent={onlineCount === nodes.length ? 'green' : onlineCount > 0 ? 'cyan' : 'red'}
            />
            <Card className="tg-mini-card">
              <CardContent className="p-3.5">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Активный
                  </span>
                  <div className="rounded-md bg-muted p-1.5 text-primary">
                    <Server size={15} aria-hidden />
                  </div>
                </div>
                <p className="mt-2 truncate text-base font-bold leading-tight">
                  {activeNode?.name ?? '—'}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {activeNode ? NODE_STATUS_LABELS[activeNode.status] : 'не выбран'}
                </p>
              </CardContent>
            </Card>
          </div>

          {activeNode && (
            <Card
              className={cn(
                'tg-mini-summary-card',
                activeNode.status === 'online' ? 'is-active' : 'is-idle',
              )}
            >
              <CardContent className="flex items-center justify-between gap-3 p-3.5">
                <div className="min-w-0">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Сейчас используется
                  </p>
                  <p className="mt-1 truncate text-sm font-semibold">{activeNode.name}</p>
                  <p className="mono mt-0.5 text-xs text-muted-foreground">{nodeAddress(activeNode)}</p>
                </div>
                <NodeStatusBadge status={activeNode.status} />
              </CardContent>
            </Card>
          )}

          <div className="space-y-2">
            <MiniListToolbar
              search={search}
              onSearchChange={setSearch}
              searchPlaceholder="Поиск по имени, хосту, IP…"
            />
            <div className="tg-mini-segmented tg-mini-segmented--cols-4" role="tablist" aria-label="Фильтр статуса">
              {STATUS_FILTERS.map((option) => {
                const count = statusCounts[option.value]
                const active = statusFilter === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    className={cn('tg-mini-segment', active && 'is-active')}
                    onClick={() => setStatusFilter(option.value)}
                  >
                    <span>{option.label}</span>
                    <span className="tg-mini-segment-count">{count}</span>
                  </button>
                )
              })}
            </div>
            {hasActiveFilters && (
              <p className="tg-mini-results-meta">
                Показано {filteredNodes.length}
                {filteredNodes.length !== nodes.length ? ` из ${nodes.length}` : ''}
              </p>
            )}
          </div>
        </>
      )}

      {nodes.length === 0 ? (
        <div className="tg-mini-filter-empty">
          <Server size={22} className="text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">Узлы не найдены</p>
          <p className="text-xs text-muted-foreground">Добавьте VPN-узел в веб-панели</p>
        </div>
      ) : filteredNodes.length === 0 ? (
        <div className="tg-mini-filter-empty">
          <Search size={20} className="text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">Ничего не найдено</p>
          <p className="text-xs text-muted-foreground">Измените поиск или сбросьте фильтр</p>
          <Button type="button" variant="outline" size="sm" className="mt-1" onClick={resetFilters}>
            Сбросить
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredNodes.map((node) => {
            const isActive = node.id === activeNodeId || node.is_active
            return (
              <MiniNodeCard
                key={node.id}
                node={node}
                isActive={isActive}
                busy={busy}
                flash={flashByNode[node.id]}
                onHealth={() => void handleHealth(node.id)}
                onActivate={() => void handleActivate(node.id)}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
