import { Activity, Network, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { getAwg2Monitoring } from '@/api/client'
import Awg2ClientStatsSheet from '@/components/awg2/Awg2ClientStatsSheet'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import Spinner from '@/components/ui/Spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import type { Awg2HealthResponse, Awg2MonitoringResponse } from '@/types'

interface MonitoringTabProps {
  health: Awg2HealthResponse | null
}

function formatAge(seconds?: number | null) {
  if (seconds == null || Number.isNaN(seconds)) return '—'
  if (seconds < 60) return `${seconds}с`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}м`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}ч`
  return `${Math.floor(seconds / 86400)}д`
}

export default function MonitoringTab({ health }: MonitoringTabProps) {
  const { activeNode } = useNode()
  const { error: notifyError } = useNotifications()
  const disabled = !health?.installed

  const [data, setData] = useState<Awg2MonitoringResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [statsClientName, setStatsClientName] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (disabled) {
      setData(null)
      setLoading(false)
      setLoadError(null)
      return
    }
    setLoading(true)
    setLoadError(null)
    try {
      const result = await getAwg2Monitoring()
      setData(result)
    } catch (err) {
      setData(null)
      const message = err instanceof Error ? err.message : 'Не удалось загрузить мониторинг'
      setLoadError(message)
      notifyError(message)
    } finally {
      setLoading(false)
    }
  }, [disabled, notifyError])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  const clients = data?.clients ?? []
  const ifaces = data?.ifaces ?? []
  const onlineCount = clients.filter((c) => c.online).length

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="gap-1.5">
            <Activity className="h-3.5 w-3.5" />
            Онлайн {onlineCount}/{clients.length}
          </Badge>
          {data && (
            <Badge variant={data.stats_available ? 'success' : 'secondary'}>
              {data.stats_available ? 'stats.db' : 'live dump'}
            </Badge>
          )}
        </div>
        <Button type="button" variant="secondary" size="sm" onClick={() => void load()} disabled={loading || disabled}>
          <RefreshCw className={cn('mr-1.5 h-4 w-4', loading && 'animate-spin')} />
          Обновить
        </Button>
      </div>

      {loadError && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {loadError}
        </p>
      )}

      {loading && !data ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {ifaces.length === 0 ? (
              <div className="rounded-lg border border-dashed bg-card/40 px-4 py-6 text-sm text-muted-foreground sm:col-span-2">
                Интерфейсы не найдены в services.env
              </div>
            ) : (
              ifaces.map((iface) => (
                <div key={iface.name} className="rounded-lg border bg-card/50 p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Network className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 space-y-1">
                      <p className="font-mono text-sm font-medium">{iface.name}</p>
                      <p className="text-xs text-muted-foreground">
                        Пиров: {iface.peer_count ?? 0}
                        {iface.port ? ` · порт ${iface.port}` : ''}
                        {iface.subnet ? ` · ${iface.subnet}` : ''}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="overflow-hidden rounded-lg border bg-card/50">
            <div className="border-b px-4 py-3">
              <h3 className="text-sm font-medium">Клиенты</h3>
              <p className="text-xs text-muted-foreground">
                Нажмите на строку, чтобы открыть endpoint, GeoIP и дневную статистику клиента.
              </p>
            </div>
            {clients.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted-foreground">Нет данных по клиентам</p>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Имя</TableHead>
                      <TableHead>Статус</TableHead>
                      <TableHead>Iface</TableHead>
                      <TableHead>Handshake</TableHead>
                      <TableHead className="text-right">↓ RX</TableHead>
                      <TableHead className="text-right">↑ TX</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {clients.map((client) => (
                      <TableRow
                        key={`${client.iface ?? ''}-${client.name}-${client.pubkey ?? ''}`}
                        className="cursor-pointer"
                        onClick={() => setStatsClientName(client.name)}
                      >
                        <TableCell className="font-medium">{client.name}</TableCell>
                        <TableCell>
                          <Badge variant={client.online ? 'success' : 'secondary'}>
                            {client.online ? 'online' : 'offline'}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {client.iface || '—'}
                        </TableCell>
                        <TableCell className="tabular-nums text-muted-foreground">
                          {formatAge(client.handshake_age_s)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {formatBytes(client.rx ?? 0)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {formatBytes(client.tx ?? 0)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </>
      )}

      <Awg2ClientStatsSheet
        clientName={statsClientName}
        open={statsClientName != null}
        onOpenChange={(open) => {
          if (!open) setStatsClientName(null)
        }}
      />
    </div>
  )
}
