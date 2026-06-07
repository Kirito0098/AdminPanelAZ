import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, Globe, Network, Server, Users } from 'lucide-react'
import { ApiError, getMonitoring } from '@/api/client'
import MonitoringCharts, { formatBytes, totalTraffic } from '@/components/monitoring/MonitoringCharts'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import MetricCard from '@/components/noc/MetricCard'
import ServiceMatrix from '@/components/noc/ServiceMatrix'
import StatusPanel from '@/components/noc/StatusPanel'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import Spinner from '@/components/ui/Spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { NodeBadge } from '@/components/NodeSelector'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import type { MonitoringOverview } from '@/types'

const REFRESH_INTERVAL = 30

export default function MonitoringPage() {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal } = useProgress()
  const [data, setData] = useState<MonitoringOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const loadRef = useRef<(opts?: { initial?: boolean; manual?: boolean }) => Promise<void>>()

  const load = useCallback(
    async (opts: { initial?: boolean; manual?: boolean } = {}) => {
      const { initial = false, manual = false } = opts
      if (initial) {
        setLoading(true)
        startGlobal()
      } else if (manual) {
        setRefreshing(true)
      }
      try {
        setData(await getMonitoring())
        if (manual) success('Данные мониторинга обновлены')
        setCountdown(REFRESH_INTERVAL)
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки мониторинга')
      } finally {
        setLoading(false)
        setRefreshing(false)
        if (initial) doneGlobal()
      }
    },
    [startGlobal, doneGlobal, success, notifyError],
  )

  loadRef.current = load

  useEffect(() => {
    load({ initial: true })
  }, [load])

  useEffect(() => {
    if (!autoRefresh) return

    const tick = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          loadRef.current?.()
          return REFRESH_INTERVAL
        }
        return c - 1
      })
    }, 1000)

    return () => clearInterval(tick)
  }, [autoRefresh])

  const activeServices = data?.services.filter((s) => s.active).length ?? 0
  const wgActive = data?.wireguard_peers.filter((p) => p.latest_handshake).length ?? 0
  const totalConnections = (data?.openvpn_clients.length ?? 0) + wgActive
  const allHealthy = data ? activeServices === data.services.length : false

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Activity size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold tracking-tight">NOC · Мониторинг</h2>
              <NodeBadge name={activeNode?.name ?? data?.node_name} status={activeNode?.status} />
            </div>
            <p className="mono text-sm text-muted-foreground">LIVE · службы · подключения · трафик</p>
          </div>
        </div>
        <AutoRefreshControl
          enabled={autoRefresh}
          onToggle={() => setAutoRefresh((v) => !v)}
          countdown={countdown}
          intervalSec={REFRESH_INTERVAL}
          refreshing={refreshing}
          onManualRefresh={() => load({ manual: true })}
        />
      </div>

      {refreshing && <InlineProgressBar active label="Обновление данных..." />}

      {loading && !data ? (
        <div className="py-16">
          <Spinner label="Загрузка NOC..." />
        </div>
      ) : (
        data && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="IP сервера" value={data.server_ip || '—'} icon={Globe} accent="cyan" />
              <MetricCard
                label="Службы"
                value={`${activeServices}/${data.services.length}`}
                icon={Server}
                accent={allHealthy ? 'green' : 'amber'}
                sub={allHealthy ? 'Все online' : 'Есть offline'}
              />
              <MetricCard
                label="Подключения"
                value={totalConnections}
                icon={Users}
                accent="green"
                sub={`OVPN ${data.openvpn_clients.length} · WG ${wgActive}`}
              />
              <MetricCard
                label="Трафик (сессии)"
                value={formatBytes(totalTraffic(data))}
                icon={Network}
                accent="cyan"
                sub={`Обновлено ${new Date(data.timestamp).toLocaleTimeString('ru-RU')}`}
              />
            </div>

            <MonitoringCharts data={data} />

            <div className="grid gap-4 xl:grid-cols-1">
              <StatusPanel title="Матрица служб" icon={Server}>
                <ServiceMatrix services={data.services} />
              </StatusPanel>

              <div className="grid gap-4 lg:grid-cols-2">
                <StatusPanel title="OpenVPN — активные клиенты" icon={Users}>
                  {data.openvpn_clients.length === 0 ? (
                    <p className="py-6 text-center text-sm text-muted-foreground">Нет активных подключений</p>
                  ) : (
                    <div className="overflow-x-auto rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Клиент</TableHead>
                            <TableHead>Real IP</TableHead>
                            <TableHead>VPN IP</TableHead>
                            <TableHead>RX</TableHead>
                            <TableHead>TX</TableHead>
                            <TableHead>С</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {data.openvpn_clients.map((c) => (
                            <TableRow key={`${c.common_name}-${c.real_address}`}>
                              <TableCell className="mono font-medium">{c.common_name}</TableCell>
                              <TableCell className="mono text-xs">{c.real_address}</TableCell>
                              <TableCell className="mono text-xs">{c.virtual_address}</TableCell>
                              <TableCell className="mono text-xs">{formatBytes(c.bytes_received)}</TableCell>
                              <TableCell className="mono text-xs">{formatBytes(c.bytes_sent)}</TableCell>
                              <TableCell className="mono text-xs">{c.connected_since}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </StatusPanel>

                <StatusPanel title="WireGuard / AmneziaWG — пиры" icon={Activity}>
                  {data.wireguard_peers.length === 0 ? (
                    <p className="py-6 text-center text-sm text-muted-foreground">Нет данных WireGuard</p>
                  ) : (
                    <div className="overflow-x-auto rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>IF</TableHead>
                            <TableHead>Клиент</TableHead>
                            <TableHead>Endpoint</TableHead>
                            <TableHead>IP</TableHead>
                            <TableHead>RX</TableHead>
                            <TableHead>TX</TableHead>
                            <TableHead>Handshake</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {data.wireguard_peers.map((p) => (
                            <TableRow
                              key={`${p.interface}-${p.public_key}`}
                              className={cn(p.latest_handshake && 'bg-emerald-500/5')}
                            >
                              <TableCell className="mono text-xs">{p.interface}</TableCell>
                              <TableCell className="mono text-xs font-medium">{p.client_name || '—'}</TableCell>
                              <TableCell className="mono text-xs">{p.endpoint || '—'}</TableCell>
                              <TableCell className="mono text-xs">{p.allowed_ips || '—'}</TableCell>
                              <TableCell className="mono text-xs">{formatBytes(p.transfer_rx)}</TableCell>
                              <TableCell className="mono text-xs">{formatBytes(p.transfer_tx)}</TableCell>
                              <TableCell className="mono text-xs">
                                {p.latest_handshake
                                  ? new Date(p.latest_handshake).toLocaleString('ru-RU')
                                  : '—'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </StatusPanel>
              </div>
            </div>
          </>
        )
      )}
    </div>
  )
}
