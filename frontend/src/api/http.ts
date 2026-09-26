import { apiBase as API_BASE } from '@/lib/panelBase'
import { parseHttpErrorBody } from '@/lib/httpErrorMessage'
import { clearAccessToken, getAccessToken, setAccessToken } from '@/lib/accessToken'
import { getActiveTimeZone } from '@/lib/datetime'
import {
  applyExpectedNodeHeader,
  isActiveNodeChangedPayload,
  notifyActiveNodeChanged,
} from '@/lib/expectedNode'
import { getWebSessionId } from '@/lib/webSession'

export class ApiError extends Error {
  status: number
  payload?: unknown
  constructor(message: string, status: number, payload?: unknown) {
    super(message)
    this.status = status
    this.payload = payload
  }
}

/** @deprecated Prefer getAccessToken — kept as alias for existing API modules. */
export function getToken(): string | null {
  return getAccessToken()
}

export function isNodeAgentAuthFailureDetail(detail: unknown): boolean {
  if (typeof detail === 'object' && detail && 'code' in detail) {
    const code = (detail as { code?: unknown }).code
    if (code === 'node_auth') return true
  }
  const text =
    typeof detail === 'string'
      ? detail
      : Array.isArray(detail) && detail.length > 0 && typeof detail[0] === 'string'
        ? detail[0]
        : typeof detail === 'object' && detail && 'message' in detail && typeof (detail as { message: unknown }).message === 'string'
          ? (detail as { message: string }).message
          : typeof detail === 'object' && detail && 'msg' in detail && typeof (detail as { msg: unknown }).msg === 'string'
            ? (detail as { msg: string }).msg
            : ''
  if (!text) return false
  return text.includes('X-Node-Key') || text.includes('Неверный API-ключ')
}

const SERVER_UNREACHABLE_MESSAGE =
  'Не удалось связаться с сервером. Возможен перезапуск панели — подождите и откройте новый адрес.'
export const REFRESH_TIMEOUT_MS = 20_000

let refreshPromise: Promise<string | null> | null = null

function isServerUnavailableStatus(status: number): boolean {
  return status >= 500 || status === 408 || status === 429
}

/**
 * Resolves to null only when the server refuses the session (it is cleared then).
 * An unreachable or failing server rejects with ApiError and keeps the session for a retry.
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), REFRESH_TIMEOUT_MS)
    refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      signal: controller.signal,
    })
      .catch(() => {
        throw new ApiError(SERVER_UNREACHABLE_MESSAGE, 0)
      })
      .then(async (response) => {
        if (!response.ok) {
          if (isServerUnavailableStatus(response.status)) {
            throw new ApiError(parseHttpErrorBody(await response.text(), response.status), response.status)
          }
          clearAccessToken()
          return null
        }
        const data = await response.json()
        const token = data.access_token as string
        setAccessToken(token)
        return token
      })
      .finally(() => {
        clearTimeout(timer)
        refreshPromise = null
      })
  }
  return refreshPromise
}

export async function apiFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  return apiFetchAtBase<T>(API_BASE, path, options, retry)
}

export async function apiFetchAtBase<T>(
  base: string,
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const sessionId = getWebSessionId()
  if (sessionId) headers.set('X-Web-Session-Id', sessionId)
  if (!headers.has('X-Client-Timezone')) {
    const tz = getActiveTimeZone()
    if (tz) headers.set('X-Client-Timezone', tz)
  }

  const normalizedBase = base.endsWith('/') ? base.slice(0, -1) : base
  if (normalizedBase === API_BASE) applyExpectedNodeHeader(headers, options.method)
  let response: Response
  try {
    response = await fetch(`${normalizedBase}${path}`, { ...options, headers, credentials: 'include' })
  } catch {
    throw new ApiError(SERVER_UNREACHABLE_MESSAGE, 0)
  }
  if (response.status === 401 && retry && !path.startsWith('/auth/') && normalizedBase === API_BASE) {
    const body = await response.text()
    let payload: unknown
    try {
      payload = body ? JSON.parse(body) : undefined
    } catch {
      payload = undefined
    }
    const detail =
      payload && typeof payload === 'object' && payload !== null && 'detail' in payload
        ? (payload as { detail: unknown }).detail
        : body
    if (isNodeAgentAuthFailureDetail(detail)) {
      const message = parseHttpErrorBody(body, 401)
      throw new ApiError(message, 401, payload)
    }
    const newToken = await refreshAccessToken()
    if (newToken) {
      return apiFetchAtBase<T>(base, path, options, false)
    }
    clearAccessToken()
    const message = parseHttpErrorBody(body, 401)
    throw new ApiError(message, 401, payload)
  }
  if (!response.ok) {
    const body = await response.text()
    let payload: unknown
    if (body) {
      try {
        payload = JSON.parse(body)
      } catch {
        payload = undefined
      }
    }
    if (response.status === 409 && isActiveNodeChangedPayload(payload)) notifyActiveNodeChanged()
    const detail = parseHttpErrorBody(body, response.status)
    throw new ApiError(detail, response.status, payload)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export { API_BASE }

export async function parseApiError(response: Response, fallback: string): Promise<ApiError> {
  const body = await response.text()
  const detail = parseHttpErrorBody(body, response.status, fallback)
  return new ApiError(detail, response.status)
}
