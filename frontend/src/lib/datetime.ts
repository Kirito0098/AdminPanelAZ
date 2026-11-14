/**
 * Centralised date/time formatting that respects the user's chosen timezone.
 *
 * Backend timestamps are stored as naive UTC (datetime.utcnow), i.e. without a
 * timezone designator. Such strings must be interpreted as UTC and then rendered
 * in the active timezone — otherwise the browser would treat them as local time
 * and show "server time" shifted by the local offset.
 */

const RU_LOCALE = 'ru-RU'

let activeTimeZone: string | undefined

export function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

/** Set the active timezone. Empty/nullish means "use the browser default". */
export function setActiveTimeZone(tz: string | null | undefined): void {
  const value = (tz ?? '').trim()
  activeTimeZone = value || undefined
}

/** The timezone actually used for formatting (resolves to browser when unset). */
export function getActiveTimeZone(): string {
  return activeTimeZone || getBrowserTimeZone()
}

const ISO_TS_RE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/
const ZONE_SUFFIX_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i

function toDate(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value === 'number') {
    const d = new Date(value)
    return Number.isNaN(d.getTime()) ? null : d
  }
  let s = String(value).trim()
  if (!s) return null
  if (/\sUTC$/i.test(s)) {
    // "YYYY-MM-DD HH:MM:SS UTC" -> ISO with an explicit zone.
    s = `${s.slice(0, -4).replace(' ', 'T')}Z`
  } else if (ISO_TS_RE.test(s) && !ZONE_SUFFIX_RE.test(s)) {
    // Naive backend timestamp (no timezone) -> interpret as UTC.
    s = `${s.replace(' ', 'T')}Z`
  }
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Parse a backend timestamp into a Date, treating naive values as UTC. */
export function parseTimestamp(value: string | number | Date | null | undefined): Date | null {
  return toDate(value)
}

function withTz(opts?: Intl.DateTimeFormatOptions): Intl.DateTimeFormatOptions {
  return activeTimeZone ? { timeZone: activeTimeZone, ...opts } : { ...opts }
}

type DateInput = string | number | Date | null | undefined

/** `<input type="date">` (`YYYY-MM-DD`) → ISO конца этого дня в локальной зоне. */
export function endOfDayIso(value: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 23, 59, 59, 999).toISOString()
}

/** Full date + time, e.g. "18.06.2026, 11:45:00" in the active timezone. */
export function formatDateTime(value: DateInput, opts?: Intl.DateTimeFormatOptions, fallback = '—'): string {
  const d = toDate(value)
  if (!d) return fallback
  try {
    return d.toLocaleString(RU_LOCALE, withTz(opts))
  } catch {
    return fallback
  }
}

/** Date only, e.g. "18.06.2026". */
export function formatDate(value: DateInput, opts?: Intl.DateTimeFormatOptions, fallback = '—'): string {
  const d = toDate(value)
  if (!d) return fallback
  try {
    return d.toLocaleDateString(RU_LOCALE, withTz(opts))
  } catch {
    return fallback
  }
}

/** Time only, e.g. "11:45:00". */
export function formatTime(value: DateInput, opts?: Intl.DateTimeFormatOptions, fallback = '—'): string {
  const d = toDate(value)
  if (!d) return fallback
  try {
    return d.toLocaleTimeString(RU_LOCALE, withTz(opts))
  } catch {
    return fallback
  }
}

const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

/**
 * Относительное время в активном поясе: «только что», «5 мин назад», «2 ч назад»,
 * «вчера», «3 дн назад», иначе дата. Для дат из будущего/рассинхрона — «только что».
 */
export function formatRelative(value: DateInput, now: number = Date.now(), fallback = '—'): string {
  const d = toDate(value)
  if (!d) return fallback
  const diff = now - d.getTime()
  if (diff < MINUTE_MS) return 'только что'
  if (diff < HOUR_MS) return `${Math.floor(diff / MINUTE_MS)} мин назад`
  if (diff < DAY_MS) return `${Math.floor(diff / HOUR_MS)} ч назад`
  const days = Math.floor(diff / DAY_MS)
  if (days === 1) return 'вчера'
  if (days < 30) return `${days} дн назад`
  return formatDate(value)
}

/** Short label of the active timezone, e.g. "UTC+3" / "MSK", for hints. */
export function getTimeZoneLabel(tz?: string): string {
  const zone = tz || getActiveTimeZone()
  try {
    const parts = new Intl.DateTimeFormat(RU_LOCALE, {
      timeZone: zone,
      timeZoneName: 'shortOffset',
    }).formatToParts(new Date())
    const name = parts.find((p) => p.type === 'timeZoneName')?.value
    return name || zone
  } catch {
    return zone
  }
}
