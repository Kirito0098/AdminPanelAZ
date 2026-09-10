/** Client-side traffic custom-period bounds and validation (local calendar days). */

function startOfLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

/** Inclusive window: [today - retentionDays … today]. */
export function availableDateBounds(
  retentionDays: number,
  today: Date = new Date(),
): { min: Date; max: Date } {
  const max = startOfLocalDay(today)
  const min = new Date(max)
  min.setDate(min.getDate() - retentionDays)
  return { min, max }
}

/** Russian error when range is invalid; null when OK. */
export function validateCustomRange(
  from: Date,
  to: Date,
  retentionDays: number,
  today: Date = new Date(),
): string | null {
  const err =
    `Нельзя: данные трафика хранятся ${retentionDays} дней (Настройки → Обслуживание).`
  if (!Number.isFinite(retentionDays) || retentionDays < 1) return err

  const fromDay = startOfLocalDay(from)
  const toDay = startOfLocalDay(to)
  const { min, max } = availableDateBounds(retentionDays, today)

  if (fromDay.getTime() > toDay.getTime()) return err
  if (fromDay.getTime() > max.getTime() || toDay.getTime() > max.getTime()) return err
  if (fromDay.getTime() < min.getTime() || toDay.getTime() < min.getTime()) return err

  const spanDays = Math.round((toDay.getTime() - fromDay.getTime()) / 86400000)
  if (spanDays > retentionDays) return err

  return null
}

/** Format local date as YYYY-MM-DD for API query params. */
export function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Parse YYYY-MM-DD as local calendar day (noon-safe via Y/M/D ctor). */
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
): boolean {
  const from = parseLocalDate(fromIso)
  const to = parseLocalDate(toIso)
  if (!from || !to) return false
  return validateCustomRange(from, to, retentionDays, today) == null
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
  if (preset === '1d') return '1д'
  if (preset === '7d') return '7д'
  return '30д'
}
