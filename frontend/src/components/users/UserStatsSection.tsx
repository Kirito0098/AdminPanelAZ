import { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { ChartResponsive } from '@/components/monitoring/ChartResponsive'
import { getUserStats } from '@/api/users'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatBytes } from '@/lib/trafficFormat'
import { formatDateTime } from '@/lib/datetime'

interface UserStatsSectionProps {
  userId: number
}

const DAILY_COLOR = 'oklch(0.65 0.2 260)'

export default function UserStatsSection({ userId }: UserStatsSectionProps) {
  const { isEnabled } = useFeatureModules()
  const { error: notifyError } = useNotifications()
  const trafficSync = isEnabled('traffic_sync')
  const [stats, setStats] = useState<Awaited<ReturnType<typeof getUserStats>> | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        const data = await getUserStats(userId, 30)
        if (!cancelled) setStats(data)
      } catch (err) {
        if (!cancelled) notifyError(err instanceof Error ? err.message : 'Ошибка загрузки статистики')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [userId, notifyError])

  if (loading) return null
  if (!trafficSync) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Статистика</CardTitle>
          <CardDescription>Сбор трафика и история подключений.</CardDescription>
        </CardHeader>
        <CardContent className="py-6 text-center text-muted-foreground">
          Сбор трафика выключен в Модулях. Включите «Мониторинг трафика», чтобы увидеть статистику абонента.
        </CardContent>
      </Card>
    )
  }
  if (!stats) return null

  const rows = stats.rows
  const totals = stats.totals

  const lastSeen = rows.reduce<Date | null>((best, row) => {
    if (!row.last_seen_at) return best
    const d = new Date(row.last_seen_at)
    if (best == null || d > best) return d
    return best
  }, null)

  // агрегируем дневные байты по всем конфигам
  const dailyMap = new Map<string, number>()
  for (const row of rows) {
    for (const point of row.daily ?? []) {
      dailyMap.set(point.date, (dailyMap.get(point.date) ?? 0) + point.bytes)
    }
  }
  const dailyPoints = Array.from(dailyMap.entries())
    .map(([date, bytes]) => ({ date, bytes }))
    .sort((a, b) => a.date.localeCompare(b.date))

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Статистика за 30 дней</CardTitle>
          <CardDescription>
            Все узлы и протоколы абонента. Тень HA складывается в первичный узел.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 p-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard title="Получено" value={formatBytes(totals.received)} />
            <StatCard title="Отправлено" value={formatBytes(totals.sent)} />
            <StatCard title="Всего за период" value={formatBytes(totals.bytes)} sessions={totals.sessions} />
          </div>
          {lastSeen && (
            <p className="text-xs text-muted-foreground">
              Последнее подключение: {formatDateTime(lastSeen)}
            </p>
          )}
          {!lastSeen && (
            <p className="text-xs text-muted-foreground">Ещё не подключался</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>График трафика (30 дней)</CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <ChartResponsive height={220} className="w-full">
            {({ width }) => (
              <ResponsiveContainer width={width} height={220}>
                <AreaChart data={dailyPoints}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                  <Legend />
                  <Area type="monotone" dataKey="bytes" fill={DAILY_COLOR} stroke={DAILY_COLOR} fillOpacity={0.35} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </ChartResponsive>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>По конфигам</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Узел</TableHead>
                <TableHead>Протокол</TableHead>
                <TableHead className="text-right">Трафик 30 дн.</TableHead>
                <TableHead className="text-right">Всего</TableHead>
                <TableHead className="text-right">Сессий</TableHead>
                <TableHead className="text-right">Последний раз</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={`${row.node_id}-${row.vpn_type}`}>
                  <TableCell className="font-mono text-xs">{row.node_id}</TableCell>
                  <TableCell className="text-xs">{row.vpn_type}</TableCell>
                  <TableCell className="text-right text-xs font-mono">{formatBytes(row.period_bytes)}</TableCell>
                  <TableCell className="text-right text-xs font-mono">{formatBytes(row.total_bytes)}</TableCell>
                  <TableCell className="text-right text-xs">{row.total_sessions}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {row.last_seen_at ? formatDateTime(row.last_seen_at) : '—'}
                  </TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-xs text-muted-foreground text-center">
                    Нет данных
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

function StatCard({
  title,
  value,
  sessions,
}: {
  title: string
  value: string
  sessions?: number
}) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <p className="text-xs text-muted-foreground">{title}</p>
      <div className="flex items-baseline gap-1 mt-1">
        <span className="text-sm font-semibold">{value}</span>
        {sessions != null && <span className="text-xs text-muted-foreground"> · {sessions} сессий</span>}
      </div>
    </div>
  )
}
