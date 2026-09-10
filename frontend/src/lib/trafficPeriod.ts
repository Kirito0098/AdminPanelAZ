/** Client-side traffic custom-period bounds and validation (panel timezone calendar days). */

import { getActiveTimeZone } from '@/lib/datetime'

/** YYYY-MM-DD for `instant` in `timeZone` (falls back to browser local on bad zone). */
export function calendarDateInZone(instant: Date, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(instant)
  } catch {
    return formatLocalDate(instant)
  }
}

/** Panel "today" as a local Date bag (Y/M/D match panel calendar day). */
export function panelToday(instant: Date = new Date(), timeZone: string = getActiveTimeZone()): Date {
  const iso = calendarDateInZone(instant, timeZone)
  const parsed = parseLocalDate(iso)
  return parsed ?? startOfLocalDay(instant)
}

function startOfLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

/** Inclusive window: [today - retentionDays … today] in panel (or given) timezone. */
export function availableDateBounds(
  retentionDays: number,
  today: Date = new Date(),
  timeZone: string = getActiveTimeZone(),
): { min: Date; max: Date } {
  const max = panelToday(today, timeZone)
  const min = new Date(max)
  min.setDate(min.getDate() - retentionDays)
  return { min, max }
}

const MSG_ORDER = 'Дата «от» не может быть позже даты «до».'
const MSG_FUTURE = 'Нельзя выбрать дату в будущем.'

function retentionMessage(retentionDays: number): string {
  return `Нельзя: данные трафика хранятся ${retentionDays} дней (Настройки → Обслуживание).`
}

/** Russian error when range is invalid; null when OK. */
export function validateCustomRange(
  from: Date,
  to: Date,
  retentionDays: number,
  today: Date = new Date(),
  timeZone: string = getActiveTimeZone(),
): string | null {
  if (!Number.isFinite(retentionDays) || retentionDays < 1) {
    return retentionMessage(Number.isFinite(retentionDays) ? retentionDays : 0)
  }

  const fromDay = startOfLocalDay(from)
  const toDay = startOfLocalDay(to)
  const { min, max } = availableDateBounds(retentionDays, today, timeZone)

  if (fromDay.getTime() > toDay.getTime()) return MSG_ORDER
  if (fromDay.getTime() > max.getTime() || toDay.getTime() > max.getTime()) return MSG_FUTURE
  if (fromDay.getTime() < min.getTime() || toDay.getTime() < min.getTime()) {
    return retentionMessage(retentionDays)
  }

  const spanDays = Math.round((toDay.getTime() - fromDay.getTime()) / 86400000)
  if (spanDays > retentionDays) return retentionMessage(retentionDays)

  return null
}

/** Format local date bag as YYYY-MM-DD for API query params. */
export function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Parse YYYY-MM-DD as local calendar day bag (noon-safe via Y/M/D ctor). */
export function parseLocalDate(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.trim())
  if (!m) return null
  const y = Number(m[1])
  const mo = Number(m[2])
  const d = Number(m[3])
  const date = new Date(y, mo - 1, d)
  if (date.getFullYear() !== y || date.getMonth() !== mo - 1 || date.getDate() !== d) {
    return null
  }
  return date
}

/** True when ISO from/to parse and pass validateCustomRange for retention. */
export function isAppliedCustomValid(
  fromIso: string,
  toIso: string,
  retentionDays: number,
  today: Date = new Date(),
  timeZone: string = getActiveTimeZone(),
): boolean {
  const from = parseLocalDate(fromIso)
  const to = parseLocalDate(toIso)
  if (!from || !to) return false
  return validateCustomRange(from, to, retentionDays, today, timeZone) == null
}

/** Detect overview/chart 400s caused by period validation. */
export function isTrafficPeriodHttpError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const status = (err as { status?: unknown }).status
  if (status !== 400) return false
  const message = String((err as { message?: unknown }).message ?? '')
  return (
    /хранят/i.test(message) ||
    /период/i.test(message) ||
    /дат/i.test(message) ||
    /ГГГГ-ММ-ДД/i.test(message) ||
    /будущ/i.test(message)
  )
}

/** Short RU label for overview preset or applied custom range. */
export function overviewPeriodSubtitle(
  mode: 'preset' | 'custom',
  preset: '1d' | '7d' | '30d',
  appliedFrom: string,
  appliedTo: string,
): string {
  if (mode === 'custom' && appliedFrom && appliedTo) {
    return `${appliedFrom} — ${appliedTo}`
  }
  if (mode === 'custom') return 'не применено'
  if (preset === '1d') return '1д'
  if (preset === '7d') return '7д'
  return '30д'
}
