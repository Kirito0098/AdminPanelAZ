import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, BarChart3 } from 'lucide-react'
import { getWarperTraffic } from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { WarperHealthResponse } from '@/types'
import WarperTrafficChart, { type WarperTrafficChartPoint } from './WarperTrafficChart'
import { WarperStatTile } from './WarperSection'
import { formatBytes } from './utils'

const PERIODS = [
  { key: 'today', label: 'Сегодня' },
  { key: 'week', label: 'Неделя' },
  { key: 'month', label: 'Месяц' },
  { key: 'all', label: 'Всё время' },
] as const

type PeriodKey = (typeof PERIODS)[number]['key']

interface TrafficTabProps {
  health: WarperHealthResponse | null
  embedded?: boolean
  hideTitle?: boolean
}

function readTrafficNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function readTraffic(data: Record<string, unknown>) {
  return {
    rx:
      readTrafficNumber(data.period_rx) ??
      readTrafficNumber(data.rx) ??
      readTrafficNumber(data.today_rx),
    tx:
      readTrafficNumber(data.period_tx) ??
      readTrafficNumber(data.tx) ??
      readTrafficNumber(data.today_tx),
    uptime: typeof data.uptime === 'string' ? data.uptime : null,
    summary: typeof data.summary === 'string' ? data.summary : null,
  }
}

function readChartNumber(value: unknown): number {
  return readTrafficNumber(value) ?? 0
}

function readChartPoints(data: Record<string, unknown>, period: string): WarperTrafficChartPoint[] {
  const chart = data.chart
  if (Array.isArray(chart)) {
    const points: WarperTrafficChartPoint[] = []
    for (const item of chart) {
      if (!item || typeof item !== 'object') continue
      const row = item as Record<string, unknown>
      const label = typeof row.label === 'string' ? row.label : ''
      const rx = readChartNumber(row.rx)
      const tx = readChartNumber(row.tx)
      if (!label) continue
      points.push({ label, rx, tx })
    }
    if (points.length > 0) return points
  }

  const hourly = data.hourly_points
  if (Array.isArray(hourly) && hourly.length > 0) {
    const points: WarperTrafficChartPoint[] = []
    for (const item of hourly) {
      if (!item || typeof item !== 'object') continue
      const row = item as Record<string, unknown>
      const ts = typeof row.ts === 'string' ? row.ts : ''
      const rx = readChartNumber(row.rx)
      const tx = readChartNumber(row.tx)
      if (!ts) continue
      const label =
        period === 'today'
          ? `${ts.split('T', 1)[1]?.slice(0, 2) ?? ts}:00`
          : (() => {
              const day = ts.slice(0, 10)
              const parts = day.split('-')
              return parts.length === 3 ? `${parts[2]}.${parts[1]}` : ts.slice(5)
            })()
      points.push({ label, rx, tx })
    }
    if (points.length > 0) return points
  }

  const rx = readChartNumber(data.period_rx) || readChartNumber(data.today_rx)
  const tx = readChartNumber(data.period_tx) || readChartNumber(data.today_tx)
  if (rx > 0 || tx > 0) {
    const labels: Record<string, string> = {
      today: 'Сегодня',
      week: 'Неделя',
      month: 'Месяц',
      all: 'Всё время',
    }
    return [{ label: labels[period] ?? period, rx, tx }]
  }

  return []
}

export default function TrafficTab({ health, embedded = false, hideTitle = false }: TrafficTabProps) {
  const { activeNode } = useNode()
  const { error: notifyError } = useNotifications()
  const [period, setPeriod] = useState<PeriodKey>('today')
  const [data, setData] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!health?.installed) {
      setData({})
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const response = await getWarperTraffic(period)
      setData(response.data ?? {})
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось загрузить трафик')
      setData({})
    } finally {
      setLoading(false)
    }
  }, [health?.installed, notifyError, period])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  const { rx, tx, uptime, summary } = readTraffic(data)
  const chartPoints = useMemo(() => readChartPoints(data, period), [data, period])
  const periodLabel = PERIODS.find((item) => item.key === period)?.label ?? period

  const body = (
    <>
      <div className={`flex flex-wrap items-center gap-2 ${embedded ? 'mb-4' : 'mb-4'}`}>
        <div className="flex flex-wrap gap-2">
          {PERIODS.map((item) => (
            <Button
              key={item.key}
              size="sm"
              variant={period === item.key ? 'default' : 'secondary'}
              disabled={!health?.installed || loading}
              onClick={() => setPeriod(item.key)}
            >
              {item.label}
            </Button>
          ))}
        </div>
        <Button size="sm" variant="ghost" disabled={loading} onClick={() => void load()}>
          Обновить
        </Button>
      </div>

      {loading ? (
        <div className={`flex justify-center ${embedded ? 'py-8' : 'py-10'}`}>
          <Spinner />
        </div>
      ) : !health?.installed ? (
        <p className="text-sm text-muted-foreground">Трафик доступен после установки AZ-WARP на узле.</p>
      ) : (
        <div className="space-y-4">
          {embedded ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <WarperStatTile
                label="Исходящий ↑"
                value={tx == null ? '—' : formatBytes(tx)}
              />
              <WarperStatTile
                label="Входящий ↓"
                value={rx == null ? '—' : formatBytes(rx)}
              />
              {uptime && <WarperStatTile label="Аптайм sing-box" value={uptime} />}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Исходящий ↑</CardTitle>
                  <ArrowUp className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{tx == null ? '—' : formatBytes(tx)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium text-muted-foreground">Входящий ↓</CardTitle>
                  <ArrowDown className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{rx == null ? '—' : formatBytes(rx)}</div>
                </CardContent>
              </Card>
              {uptime && (
                <Card className="sm:col-span-2 lg:col-span-2">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">Аптайм sing-box</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-lg font-semibold">{uptime}</div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          <div className="rounded-lg border bg-muted/10 p-3 sm:p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-medium">График трафика</p>
                <p className="text-xs text-muted-foreground">
                  {periodLabel} · почасовая статистика singbox-tun
                </p>
              </div>
            </div>
            <WarperTrafficChart points={chartPoints} embedded={embedded} />
          </div>

          {summary && (
            <p className="rounded-lg border bg-muted/30 p-3 font-mono text-xs">{summary}</p>
          )}
        </div>
      )}
    </>
  )

  if (embedded) {
    return <div>{!hideTitle && <h3 className="mb-3 text-sm font-semibold">Трафик WARP</h3>}{body}</div>
  }

  return (
    <StatusPanel title="Трафик WARP" icon={BarChart3}>
      {body}
    </StatusPanel>
  )
}
