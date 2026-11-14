import { apiBase as API_BASE } from '@/lib/panelBase'
import { parseHttpErrorBody } from '@/lib/httpErrorMessage'
import { clearAccessToken, getAccessToken, setAccessToken } from '@/lib/accessToken'
import { getActiveTimeZone } from '@/lib/datetime'
import {
  applyExpectedNodeHeader,
  isActiveNodeChangedPayload,
  notifyActiveNodeChanged,
} from '@/lib/expectedNode'
import { notifySessionLost } from '@/lib/sessionLost'
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

/**
 * FastAPI отдаёт `{"detail": ...}` для HTTPException, но часть 409 приходит через
 * JSONResponse с полями на верхнем уровне. Приводим payload к одной форме (объект
 * деталей), чтобы потребители читали `err.payload.code` одинаково в обоих случаях.
 */
export function unwrapErrorPayload(payload: unknown): unknown {
  if (payload && typeof payload === 'object' && payload !== null && 'detail' in payload) {
    return (payload as { detail: unknown }).detail
  }
  return payload
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
const REFRESH_LOCK_NAME = 'az-auth-refresh'

let refreshPromise: Promise<string | null> | null = null

function isServerUnavailableStatus(status: number): boolean {
  return status >= 500 || status === 408 || status === 429
}

const NO_REFRESH_AUTH_PATHS = ['/auth/login', '/auth/logout', '/auth/refresh']

/** Sign-in (password, 2FA, passkey), logout and refresh answer 401 for bad credentials, not for an expired session. */
function refreshesSessionOn401(path: string): boolean {
  const pathname = path.split('?', 1)[0]
  return !NO_REFRESH_AUTH_PATHS.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
}

/**
 * Tabs share one refresh cookie: overlapping rotations answered out of order leave a revoked token in it,
 * which the server treats as reuse once the grace window has passed.
 */
function withRefreshLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = typeof navigator === 'undefined' ? undefined : navigator.locks
  if (!locks?.request) return task()
  let granted = false
  const locked = locks.request(REFRESH_LOCK_NAME, () => {
    granted = true
    return task()
  }) as Promise<T>
  return locked.catch((error: unknown) => {
    if (granted) throw error
    return task()
  })
}

function requestRefresh(): Promise<string | null> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REFRESH_TIMEOUT_MS)
  return fetch(`${API_BASE}/auth/refresh`, {
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
        notifySessionLost()
        return null
      }
      const data = await response.json()
      const token = data.access_token as string
      setAccessToken(token)
      return token
    })
    .finally(() => clearTimeout(timer))
}

/**
 * Resolves to null only when the server refuses the session (it is cleared then).
 * An unreachable or failing server rejects with ApiError and keeps the session for a retry.
 */
export async function refreshAccessToken(): Promise<string | null> {
  refreshPromise ??= withRefreshLock(requestRefresh).finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

export interface ApiRequestContext {
  /** Base URL, no trailing slash. */
  base: string
  path: string
  options: RequestInit
}

export interface UnauthorizedContext extends ApiRequestContext {
  /** The token the rejected request carried; a caller may spot a renewal made by another request. */
  sentToken: string | null
  body: string
  payload: unknown
}

/**
 * Everything the panel and the Mini App do differently for one outgoing request.
 * The request itself — headers, timeouts, error parsing, retry-once — is shared below.
 */
export interface ApiTransport {
  /** Bearer token; null leaves the Authorization header out. */
  token: () => string | null
  /** Client-specific headers, applied before every fetch. */
  prepareHeaders?: (headers: Headers, request: ApiRequestContext) => void
  /** 401 hook: true — the session was renewed, retry once. May throw its own ApiError. */
  onUnauthorized?: (request: UnauthorizedContext) => Promise<boolean>
  /** 409 hook (panel: another tab switched the active node). */
  onConflict?: (payload: unknown) => void
  /** Turns a network failure into an ApiError; without it the original error is rethrown. */
  networkError?: (error: unknown) => Error
  credentials?: RequestCredentials
  /** Payload exposed as `ApiError.payload`; without it the payload is not attached. */
  errorPayload?: (payload: unknown) => unknown
}

const panelTransport: ApiTransport = {
  token: getAccessToken,
  prepareHeaders(headers, { base, options }) {
    const sessionId = getWebSessionId()
    if (sessionId) headers.set('X-Web-Session-Id', sessionId)
    if (!headers.has('X-Client-Timezone')) {
      const tz = getActiveTimeZone()
      if (tz) headers.set('X-Client-Timezone', tz)
    }
    if (base === API_BASE) applyExpectedNodeHeader(headers, options.method)
  },
  async onUnauthorized({ base, path, body, payload }) {
    if (base !== API_BASE || !refreshesSessionOn401(path)) return false
    const detail =
      payload && typeof payload === 'object' && payload !== null && 'detail' in payload
        ? (payload as { detail: unknown }).detail
        : body
    // A node agent's own key is not the panel session: keep the cookie and the token.
    if (isNodeAgentAuthFailureDetail(detail)) return false
    if (await refreshAccessToken()) return true
    clearAccessToken()
    return false
  },
  onConflict(payload) {
    if (isActiveNodeChangedPayload(payload)) notifyActiveNodeChanged()
  },
  networkError: () => new ApiError(SERVER_UNREACHABLE_MESSAGE, 0),
  credentials: 'include',
  errorPayload: unwrapErrorPayload,
}

/** Panel by default; the Mini App swaps it once at import for its own token and 401 policy. */
let transport: ApiTransport = panelTransport

export function setApiTransport(next: ApiTransport): void {
  transport = next
}

function errorFromBody(status: number, body: string, payload: unknown): ApiError {
  const message = parseHttpErrorBody(body, status)
  return transport.errorPayload
    ? new ApiError(message, status, transport.errorPayload(payload))
    : new ApiError(message, status)
}

function parseBody(body: string): unknown {
  if (!body) return undefined
  try {
    return JSON.parse(body)
  } catch {
    return undefined
  }
}

async function requestAtBase(
  base: string,
  path: string,
  options: RequestInit,
  retry: boolean,
): Promise<Response> {
  const resolvedBase = base.endsWith('/') ? base.slice(0, -1) : base
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = transport.token()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const request: ApiRequestContext = { base: resolvedBase, path, options }
  transport.prepareHeaders?.(headers, request)

  let response: Response
  try {
    response = await fetch(`${resolvedBase}${path}`, {
      ...options,
      headers,
      credentials: transport.credentials,
    })
  } catch (error) {
    throw transport.networkError ? transport.networkError(error) : error
  }
  if (response.status === 401 && retry && transport.onUnauthorized) {
    const body = await response.text()
    const payload = parseBody(body)
    if (await transport.onUnauthorized({ ...request, sentToken: token, body, payload })) {
      return requestAtBase(resolvedBase, path, options, false)
    }
    throw errorFromBody(401, body, payload)
  }
  if (!response.ok) {
    const body = await response.text()
    const payload = parseBody(body)
    if (response.status === 409) transport.onConflict?.(payload)
    throw errorFromBody(response.status, body, payload)
  }
  return response
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
  const response = await requestAtBase(base, path, options, retry)
  if (response.status === 204) return undefined as T
  return response.json()
}

/** For files and other non-JSON answers: the successful Response comes back unread. */
export function apiFetchResponse(path: string, options: RequestInit = {}): Promise<Response> {
  return requestAtBase(API_BASE, path, options, true)
}

export { API_BASE }
