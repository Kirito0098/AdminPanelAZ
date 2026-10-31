import { formatDate } from '@/lib/datetime'

const MINUTE = 60_000
const HOUR = 3_600_000
const DAY = 86_400_000

export type SnoozePreset = '1h' | '3h' | 'tomorrow9' | '3d'

export const SNOOZE_PRESETS: { id: SnoozePreset; label: string }[] = [
  { id: '1h', label: 'Через 1 час' },
  { id: '3h', label: 'Через 3 часа' },
  { id: 'tomorrow9', label: 'Завтра 9:00' },
  { id: '3d', label: 'Через 3 дня' },
]

/** «5 минут назад», «2 ч назад», «вчера», иначе дата — в активном поясе панели. */
export function formatRelative(value: string, now = Date.now()): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const diff = now - date.getTime()
  if (diff < MINUTE) return 'только что'
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)} мин назад`
  if (diff < DAY) return `${Math.floor(diff / HOUR)} ч назад`
  if (dayKey(value) === dayKey(new Date(now - DAY).toISOString())) return 'вчера'
  return formatDate(value, { day: '2-digit', month: 'short' })
}

/** Ключ для группировки ленты по дням в активном поясе. */
export function dayKey(value: string): string {
  return formatDate(value, { year: 'numeric', month: '2-digit', day: '2-digit' })
}

export function dayLabel(value: string, now = Date.now()): string {
  if (dayKey(value) === dayKey(new Date(now).toISOString())) return 'Сегодня'
  if (dayKey(value) === dayKey(new Date(now - DAY).toISOString())) return 'Вчера'
  return formatDate(value, { day: 'numeric', month: 'long' })
}

/** Пресет откладывания → UTC ISO с Z (сервер принимает только будущее). */
export function snoozeUntil(preset: SnoozePreset, now = new Date()): string {
  const target = new Date(now.getTime())
  if (preset === '1h') target.setHours(target.getHours() + 1)
  else if (preset === '3h') target.setHours(target.getHours() + 3)
  else if (preset === '3d') target.setDate(target.getDate() + 3)
  else {
    target.setDate(target.getDate() + 1)
    target.setHours(9, 0, 0, 0)
  }
  return target.toISOString()
}

export function isSnoozed(snoozedUntil: string | null, now = Date.now()): boolean {
  return snoozedUntil !== null && Date.parse(snoozedUntil) > now
}
