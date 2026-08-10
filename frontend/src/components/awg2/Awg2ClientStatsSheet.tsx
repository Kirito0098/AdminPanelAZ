import { Loader2, MapPin, RefreshCw, Router, Wifi } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getAwg2ClientStats } from '@/api/client'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import type { Awg2ClientStats } from '@/types'

interface Awg2ClientStatsSheetProps {
  clientName: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function formatAge(seconds?: number | null) {
  if (seconds == null || Number.isNaN(seconds)) return '—'
  if (seconds < 60) return `${seconds}с`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}м`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}ч`
  return `${Math.floor(seconds / 86400)}д`
}

function formatGeo(stats: Awg2ClientStats | null): string {
  if (!stats) return '—'
  if (!stats.geo) return 'нет GeoIP БД'
  const parts = [stats.geo.city, stats.geo.country].filter(Boolean)
  const place = parts.join(', ')
  return [place, stats.geo.isp].filter(Boolean).join(' · ') || 'нет GeoIP БД'
}

export default function Awg2ClientStatsSheet({ clientName, open, onOpenChange }: Awg2ClientStatsSheetProps) {
  const { error: notifyError } = useNotifications()
  const [stats, setStats] = useState<Awg2ClientStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = async (name: string) => {
    setLoading(true)
    setLoadError(null)
    try {
      const result = await getAwg2ClientStats(name)
      setStats(result)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Не удалось загрузить статистику клиента'
      setStats(null)
      setLoadError(message)
      notifyError(message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!open || !clientName) return
    void load(clientName)
  }, [clientName, open])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="pr-10">
          <div className="flex items-center gap-2">
            <SheetTitle>{clientName || 'Клиент'}</SheetTitle>
            {stats && <Badge variant={stats.online ? 'success' : 'secondary'}>{stats.online ? 'online' : 'offline'}</Badge>}
          </div>
          <SheetDescription>
            Deep stats AZ-AWG2: endpoint, GeoIP и дневной трафик.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4">
          <div className="flex justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={loading || !clientName}
              onClick={() => clientName && void load(clientName)}
            >
              <RefreshCw className={cn('mr-1.5 h-4 w-4', loading && 'animate-spin')} />
              Обновить
            </Button>
          </div>

          {loading && !stats ? (
            <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Загружаю статистику...
            </div>
          ) : loadError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {loadError}
            </div>
          ) : stats ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border bg-card/50 p-4">
                  <div className="mb-1 flex items-center gap-2 text-sm font-medium">
                    <Router className="h-4 w-4 text-primary" />
                    Endpoint
                  </div>
                  <p className="break-all font-mono text-sm">{stats.endpoint || '—'}</p>
                  <p className="mt-2 text-xs text-muted-foreground">Handshake: {formatAge(stats.handshake_age_s)}</p>
                </div>
                <div className="rounded-lg border bg-card/50 p-4">
                  <div className="mb-1 flex items-center gap-2 text-sm font-medium">
                    <MapPin className="h-4 w-4 text-primary" />
                    Гео
                  </div>
                  <p className="text-sm">{formatGeo(stats)}</p>
                </div>
                <div className="rounded-lg border bg-card/50 p-4">
                  <div className="mb-1 flex items-center gap-2 text-sm font-medium">
                    <Wifi className="h-4 w-4 text-primary" />
                    Lifetime RX
                  </div>
                  <p className="font-mono text-sm">{formatBytes(stats.rx_life ?? 0)}</p>
                </div>
                <div className="rounded-lg border bg-card/50 p-4">
                  <div className="mb-1 flex items-center gap-2 text-sm font-medium">
                    <Wifi className="h-4 w-4 text-primary" />
                    Lifetime TX
                  </div>
                  <p className="font-mono text-sm">{formatBytes(stats.tx_life ?? 0)}</p>
                </div>
              </div>

              <div className="overflow-hidden rounded-lg border bg-card/50">
                <div className="border-b px-4 py-3">
                  <h3 className="text-sm font-medium">Трафик по дням</h3>
                  <p className="text-xs text-muted-foreground">История из `stats.db`, если база доступна.</p>
                </div>
                {stats.daily.length === 0 ? (
                  <p className="px-4 py-8 text-center text-sm text-muted-foreground">По клиенту пока нет дневной статистики</p>
                ) : (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Дата</TableHead>
                          <TableHead className="text-right">↓ RX</TableHead>
                          <TableHead className="text-right">↑ TX</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {stats.daily.map((row) => (
                          <TableRow key={row.day}>
                            <TableCell className="font-mono text-xs">{row.day}</TableCell>
                            <TableCell className="text-right font-mono text-xs">{formatBytes(row.rx)}</TableCell>
                            <TableCell className="text-right font-mono text-xs">{formatBytes(row.tx)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
              Выберите клиента, чтобы посмотреть статистику.
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
