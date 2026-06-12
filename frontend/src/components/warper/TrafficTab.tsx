import { useCallback, useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, BarChart3 } from 'lucide-react'
import { getWarperTraffic } from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { WarperHealthResponse } from '@/types'
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

function readTraffic(data: Record<string, unknown>) {
  return {
    rx: typeof data.period_rx === 'number' ? data.period_rx : typeof data.rx === 'number' ? data.rx : null,
    tx: typeof data.period_tx === 'number' ? data.period_tx : typeof data.tx === 'number' ? data.tx : null,
    summary: typeof data.summary === 'string' ? data.summary : null,
  }
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

  const { rx, tx, summary } = readTraffic(data)

  const body = (
    <>
      <div className={`flex flex-wrap gap-2 ${embedded ? 'mb-3' : 'mb-4'}`}>
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
        <Button size="sm" variant="ghost" disabled={loading} onClick={() => void load()}>
          Обновить
        </Button>
      </div>

      {loading ? (
        <div className={`flex justify-center ${embedded ? 'py-6' : 'py-10'}`}>
          <Spinner />
        </div>
      ) : !health?.installed ? (
        <p className="text-sm text-muted-foreground">Трафик доступен после установки AZ-WARP на узле.</p>
      ) : (
        <div className={`grid gap-3 ${embedded ? 'grid-cols-1' : 'gap-4 sm:grid-cols-2'}`}>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Исходящий ↑</CardTitle>
              <ArrowUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className={`font-bold ${embedded ? 'text-2xl' : 'text-3xl'}`}>
                {tx == null ? '—' : formatBytes(tx)}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Входящий ↓</CardTitle>
              <ArrowDown className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className={`font-bold ${embedded ? 'text-2xl' : 'text-3xl'}`}>
                {rx == null ? '—' : formatBytes(rx)}
              </div>
            </CardContent>
          </Card>
          {summary && (
            <p
              className={`rounded-lg border bg-muted/30 p-3 font-mono text-xs ${embedded ? '' : 'sm:col-span-2 text-sm'}`}
            >
              {summary}
            </p>
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
