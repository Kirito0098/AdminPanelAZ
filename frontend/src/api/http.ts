import { apiBase as API_BASE } from '@/lib/panelBase'
import { parseHttpErrorBody } from '@/lib/httpErrorMessage'
import { getActiveTimeZone } from '@/lib/datetime'
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

export function getToken(): string | null {
  return localStorage.getItem('token')
}

let refreshPromise: Promise<string | null> | null = null

export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then(async (response) => {
        if (!response.ok) return null
        const data = await response.json()
        const token = data.access_token as string
        localStorage.setItem('token', token)
        return token
      })
      .finally(() => {
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
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const sessionId = getWebSessionId()
  if (sessionId) headers.set('X-Web-Session-Id', sessionId)
  if (!headers.has('X-Client-Timezone')) {
    const tz = getActiveTimeZone()
    if (tz) headers.set('X-Client-Timezone', tz)
  }

  const normalizedBase = base.endsWith('/') ? base.slice(0, -1) : base
  let response: Response
  try {
    response = await fetch(`${normalizedBase}${path}`, { ...options, headers, credentials: 'include' })
  } catch {
    throw new ApiError(
      'Не удалось связаться с сервером. Возможен перезапуск панели — подождите и откройте новый адрес.',
      0,
    )
  }
  if (response.status === 401 && retry && !path.startsWith('/auth/') && normalizedBase === API_BASE) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      return apiFetchAtBase<T>(base, path, options, false)
    }
    localStorage.removeItem('token')
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
