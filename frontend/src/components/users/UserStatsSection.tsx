import { useEffect, useState } from 'react'
import { Activity, ArrowDownToLine, ArrowUpFromLine, BarChart3, Clock, Database } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { ChartResponsive } from '@/components/monitoring/ChartResponsive'
import { getUserStats } from '@/api/users'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatBytes } from '@/lib/trafficFormat'
import { formatDateTime } from '@/lib/datetime'
import UserMetric from './UserMetric'
import UserSection from './UserSection'

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
      <UserSection
        icon={BarChart3}
        title="Статистика"
        description="Сбор трафика и история подключений."
      >
        <p className="text-sm text-muted-foreground">
          Сбор трафика выключен в Модулях. Включите «Мониторинг трафика», чтобы увидеть статистику
          абонента.
        </p>
      </UserSection>
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
    <div className="space-y-3">
      <UserSection
        icon={BarChart3}
        title="Сводка за 30 дней"
        description="Все узлы и протоколы абонента. Тень HA складывается в первичный узел."
      >
        <div className="space-y-3">
          <div className="grid gap-2 sm:grid-cols-3">
            <UserMetric icon={ArrowDownToLine} label="Получено" value={formatBytes(totals.received)} />
            <UserMetric icon={ArrowUpFromLine} label="Отправлено" value={formatBytes(totals.sent)} />
            <UserMetric
              icon={Database}
              label="Всего за период"
              value={formatBytes(totals.bytes)}
              hint={`${totals.sessions} сессий`}
            />
          </div>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden />
            {lastSeen ? `Последнее подключение: ${formatDateTime(lastSeen)}` : 'Ещё не подключался'}
          </p>
        </div>
      </UserSection>

      <UserSection
        icon={Activity}
        title="График трафика"
        description="Суммарный трафик по дням за 30 дней."
      >
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
      </UserSection>

      <UserSection
        icon={Database}
        title="По конфигам"
        description="Трафик, сессии и последняя активность по каждому узлу."
        contentClassName="p-0 sm:p-0"
      >
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
                <TableCell className="text-right font-mono text-xs">{formatBytes(row.period_bytes)}</TableCell>
                <TableCell className="text-right font-mono text-xs">{formatBytes(row.total_bytes)}</TableCell>
                <TableCell className="text-right text-xs">{row.total_sessions}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {row.last_seen_at ? formatDateTime(row.last_seen_at) : '—'}
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-xs text-muted-foreground">
                  Нет данных
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </UserSection>
    </div>
  )
}
