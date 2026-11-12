import { ApiError } from '@/api/http'
import { parseTimestamp } from '@/lib/datetime'
import type { ClientAccessUntilConflictPayload } from '@/types'

/** Обратное преобразование: серверный timestamp → значение для date-picker. */
export function isoToDateInput(value: string | null | undefined): string {
  const date = parseTimestamp(value ?? null)
  if (!date) return ''
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Разбирает 409 `access_until_conflict`. Принимает как `ApiError` от apiFetch,
 * так и уже разобранный payload — чтобы перебрасывание ошибки между слоями
 * не ломало флоу подтверждения.
 */
export function parseAccessUntilConflict(err: unknown): ClientAccessUntilConflictPayload | null {
  let payload: unknown
  if (err instanceof ApiError) {
    if (err.status !== 409) return null
    payload = err.payload
  } else {
    payload = err
  }
  if (!payload || typeof payload !== 'object') return null
  const raw = payload as Record<string, unknown>
  if (raw.code !== 'access_until_conflict') return null
  return {
    code: 'access_until_conflict',
    user_access_until: typeof raw.user_access_until === 'string' ? raw.user_access_until : null,
    client_access_until: typeof raw.client_access_until === 'string' ? raw.client_access_until : null,
  }
}
