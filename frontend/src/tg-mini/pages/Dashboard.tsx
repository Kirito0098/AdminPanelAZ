import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Copy,
  FileKey,
  Radio,
  Search,
  Server,
  Shield,
  Wifi,
  WifiOff,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { ApiError } from '@/api/client'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import MetricCard from '@/components/noc/MetricCard'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import MiniListToolbar, { matchesSearchQuery, type ProtocolFilter } from '@/tg-mini/components/MiniListToolbar'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import { formatDateTime } from '@/lib/datetime'
import { NODE_STATUS_LABELS } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import { getTgDashboard } from '@/tg-mini/api'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import type { TgMiniDashboard } from '@/types'

function DashboardSkeleton() {
  return (
    <div className="tg-mini-dashboard space-y-4" aria-busy="true" aria-label="Загрузка дашборда">
      <div className="tg-mini-skeleton tg-mini-skeleton-summary" />
      <div className="tg-mini-cards">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="tg-mini-skeleton tg-mini-skeleton-card" />
        ))}
      </div>
      <div className="tg-mini-skeleton tg-mini-skeleton-section" />
      <div className="tg-mini-skeleton tg-mini-skeleton-section" />
    </div>
  )
}

function SecondaryMetric({
  label,
  value,
  icon: Icon,
  sub,
  to,
}: {
  label: string
  value: ReactNode
  icon: LucideIcon
  sub?: string
  to?: string
}) {
  const content = (
    <Card className={cn('tg-mini-card', to && 'tg-mini-metric-link')}>
      <CardContent className="p-3.5">
        <div className="flex items-start justify-between gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
          <div className="rounded-md bg-muted p-1.5 text-muted-foreground">
            <Icon size={15} aria-hidden />
          </div>
        </div>
        <div className="mono mt-2 text-xl font-bold tracking-tight tabular-nums">{value}</div>
        {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  )

  if (to) {
    return (
      <Link to={to} className="block min-w-0">
        {content}
      </Link>
    )
  }

  return content
}

function CopyableServerIp({ ip }: { ip: string | null }) {
  const [hint, setHint] = useState<string | null>(null)

  const copy = async () => {
    if (!ip) return
    try {
      await navigator.clipboard.writeText(ip)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setHint('Скопировано')
      window.setTimeout(() => setHint(null), 1800)
    } catch {
      setHint('Не удалось скопировать')
      window.setTimeout(() => setHint(null), 1800)
    }
  }

  if (!ip) {
    return <span className="text-muted-foreground">—</span>
  }

  return (
    <button type="button" className="tg-mini-copy-ip" onClick={() => void copy()} title="Скопировать IP">
      <span className="mono truncate">{ip}</span>
      <Copy size={14} className="shrink-0 opacity-60" aria-hidden />
      {hint && <span className="tg-mini-copy-hint">{hint}</span>}
    </button>
  )
}

function FilterEmptyState({ onReset }: { onReset: () => void }) {
  return (
    <div className="tg-mini-filter-empty">
      <Search size={20} className="text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium">Ничего не найдено</p>
      <p className="text-xs text-muted-foreground">Измените поиск или сбросьте фильтр</p>
      <Button type="button" variant="outline" size="sm" className="mt-1" onClick={onReset}>
        Сбросить
      </Button>
    </div>
  )
}

export default function Dashboard() {
  const { isAdmin } = useTgAuth()
  const [data, setData] = useState<TgMiniDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [protocol, setProtocol] = useState<ProtocolFilter>('all')

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)
    try {
      setData(await getTgDashboard())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const filteredOpenVpn = useMemo(() => {
    if (!data || protocol === 'wireguard') return []
    return data.openvpn_clients.filter((client) =>
      matchesSearchQuery(String(client.common_name || ''), search),
    )
  }, [data, protocol, search])

  const filteredWireguard = useMemo(() => {
    if (!data || protocol === 'openvpn') return []
    return data.wireguard_peers.filter((peer) => {
      const label = peer.client_name || peer.public_key
      return matchesSearchQuery(label, search)
    })
  }, [data, protocol, search])

  const protocolCounts = useMemo(() => {
    if (!data) return undefined
    return {
      all: data.connected_openvpn + data.connected_wireguard,
      openvpn: data.connected_openvpn,
      wireguard: data.connected_wireguard,
    }
  }, [data])

  const resetFilters = () => {
    setSearch('')
    setProtocol('all')
  }

  const hasActiveFilters = search.trim().length > 0 || protocol !== 'all'
  const visibleConnections = filteredOpenVpn.length + filteredWireguard.length
  const totalConnections = data ? data.connected_openvpn + data.connected_wireguard : 0

  if (loading && !data) {
    return <DashboardSkeleton />
  }

  if ((error && !data) || !data) {
    return (
      <div className="tg-mini-panel tg-mini-error-state">
        <WifiOff size={28} className="text-destructive" aria-hidden />
        <p className="font-medium">Не удалось загрузить дашборд</p>
        <p className="tg-mini-muted">{error || 'Нет данных'}</p>
        <Button type="button" onClick={() => void load()}>
          Повторить
        </Button>
      </div>
    )
  }

  const totalOnline = data.connected_openvpn + data.connected_wireguard
  const totalWireguardPeers = data.total_wireguard_peers ?? data.wireguard_peers.length

  return (
    <div className="tg-mini-dashboard space-y-4">
      <MiniPageHeader
        title="Дашборд"
        subtitle={`Обновлено: ${formatDateTime(data.timestamp)}`}
        onRefresh={() => void load({ silent: true })}
        refreshing={refreshing}
      />

      {error && (
        <div className="tg-mini-inline-alert" role="alert">
          {error}
        </div>
      )}

      <div className="tg-mini-cards">
        <MetricCard
          label="OpenVPN онлайн"
          value={String(data.connected_openvpn)}
          sub="активных сессий"
          icon={Wifi}
          accent="cyan"
        />
        <MetricCard
          label="WG / AWG онлайн"
          value={String(data.connected_wireguard)}
          sub={`из ${totalWireguardPeers} пиров`}
          icon={Radio}
          accent="green"
        />
      </div>

      <div className="tg-mini-cards">
        <SecondaryMetric
          label="Всего онлайн"
          value={totalOnline}
          icon={Shield}
          sub={`OVPN ${data.connected_openvpn} · WG ${data.connected_wireguard}`}
        />
        <SecondaryMetric
          label="Конфиги"
          value={data.total_configs}
          icon={FileKey}
          sub="перейти к списку"
          to="/configs"
        />
      </div>

      <Card>
        <CardContent className="p-3.5">
          <div className="flex items-start justify-between gap-2">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">IP сервера</span>
            <div className="rounded-md bg-muted p-1.5 text-amber-600 dark:text-amber-500">
              <Server size={15} aria-hidden />
            </div>
          </div>
          <div className="mt-2">
            <CopyableServerIp ip={data.server_ip} />
          </div>
        </CardContent>
      </Card>

      {isAdmin ? (
        <div className="space-y-3">
          <MiniListToolbar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Поиск по имени клиента…"
            protocol={protocol}
            onProtocolChange={setProtocol}
            protocolCounts={protocolCounts}
          />

          {hasActiveFilters && totalConnections > 0 && (
            <p className="tg-mini-results-meta">
              Показано {visibleConnections}
              {visibleConnections !== totalConnections ? ` из ${totalConnections}` : ''} подключений
            </p>
          )}

          {totalConnections === 0 ? (
            <Card>
              <CardContent className="p-4">
                <EmptyConnections label="Нет активных подключений" />
              </CardContent>
            </Card>
          ) : visibleConnections === 0 ? (
            <FilterEmptyState onReset={resetFilters} />
          ) : (
            <>
              {(protocol === 'all' || protocol === 'openvpn') && (
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="text-base">OpenVPN</CardTitle>
                      <Badge variant={filteredOpenVpn.length > 0 ? 'success' : 'secondary'}>
                        {filteredOpenVpn.length}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {filteredOpenVpn.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Нет совпадений в OpenVPN</p>
                    ) : (
                      filteredOpenVpn.map((client, index) => (
                        <div key={index} className="tg-mini-list-item">
                          <span className="truncate font-medium">{String(client.common_name || '—')}</span>
                          <Badge variant="success">{NODE_STATUS_LABELS.online}</Badge>
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>
              )}

              {(protocol === 'all' || protocol === 'wireguard') && (
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="text-base">WG / AWG</CardTitle>
                      <Badge variant={filteredWireguard.length > 0 ? 'success' : 'secondary'}>
                        {filteredWireguard.length}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {filteredWireguard.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Нет совпадений в WG / AWG</p>
                    ) : (
                      filteredWireguard.map((peer) => (
                        <div key={peer.public_key} className="tg-mini-list-item tg-mini-list-item-stack">
                          <div className="flex w-full items-center justify-between gap-2">
                            <span className="truncate font-medium">
                              {peer.client_name || `${peer.public_key.slice(0, 8)}…`}
                            </span>
                            <Badge variant="success">{NODE_STATUS_LABELS.online}</Badge>
                          </div>
                          <span className="text-xs text-muted-foreground tabular-nums">
                            ↓ {formatBytes(peer.transfer_rx)} · ↑ {formatBytes(peer.transfer_tx)}
                          </span>
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      ) : (
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">
              Подробные списки подключений доступны администраторам. Вы видите только сводные счётчики.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function EmptyConnections({ label }: { label: string }) {
  return (
    <div className="tg-mini-empty-inline">
      <WifiOff size={18} className="text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  )
}
