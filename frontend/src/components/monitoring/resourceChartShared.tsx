import { XAxis } from 'recharts'
import { formatDate, formatDateTime, formatTime } from '@/lib/datetime'

/** Период графиков ресурсов — общий для сервера и панели. */
export type ResourceChartPeriod = '1d' | '7d' | '30d'

export const RANGE_LABELS: Record<ResourceChartPeriod, string> = {
  '1d': '1 день',
  '7d': '7 дней',
  '30d': '30 дней',
}

/** Палитра метрик: один и тот же показатель одного цвета на обоих экранах. */
export const CHART_COLORS = {
  cpu: 'hsl(187, 72%, 45%)',
  ram: 'hsl(142, 71%, 45%)',
  disk: 'hsl(38, 92%, 50%)',
  load: 'hsl(217, 33%, 55%)',
  total: 'hsl(217, 33%, 55%)',
  nginx: 'hsl(0, 62%, 50%)',
  watchdog: 'hsl(38, 92%, 50%)',
  vite: 'hsl(280, 65%, 55%)',
} as const

export const CHART_MARGIN = { top: 8, right: 8, left: 0, bottom: 0 }

export const CHART_GRID = { strokeDasharray: '3 3', opacity: 0.15, vertical: false }

/** Метка времени на оси X в зависимости от периода. */
export function formatChartLabel(ts: string, period: ResourceChartPeriod): string {
  if (period === '1d') {
    return formatTime(ts, { hour: '2-digit', minute: '2-digit' })
  }
  if (period === '7d') {
    return formatDateTime(ts, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  }
  return formatDate(ts, { day: '2-digit', month: '2-digit' })
}

/** Ось X с подписями по времени — одинаковая во всех графиках ресурсов. */
export function TimeXAxis() {
  return (
    <XAxis
      dataKey="label"
      tick={{ fontSize: 11 }}
      tickLine={false}
      axisLine={false}
      interval="preserveStartEnd"
    />
  )
}
