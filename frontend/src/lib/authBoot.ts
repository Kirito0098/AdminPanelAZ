import { ApiError } from '@/api/http'
import type { User } from '@/types'

export const SESSION_BOOT_TIMEOUT_MS = 15_000
export const SERVER_UNAVAILABLE_MESSAGE =
  'Сервер не отвечает. Проверьте подключение или подождите, если панель перезапускается.'

export type SessionBootResult =
  | { kind: 'user'; user: User }
  | { kind: 'anonymous' }
  | { kind: 'unavailable'; message: string }

interface SessionBootDeps {
  getToken: () => string | null
  refresh: () => Promise<string | null>
  getMe: () => Promise<User>
  timeoutMs?: number
}

class SessionBootTimeout extends Error {}

export interface AuthSessionState {
  user: User | null
  /** Why the session could not be checked; only a tab without a user shows it. */
  unavailable: string | null
}

export type AuthSessionEvent = { type: 'checked'; result: SessionBootResult } | { type: 'signed-out' }

/**
 * A signed-in tab keeps working when a later check cannot reach the server, and does not remember
 * that failure: when its session ends, the server has answered, so the login page is shown.
 */
export function reduceAuthSession(state: AuthSessionState, event: AuthSessionEvent): AuthSessionState {
  if (event.type === 'signed-out') return { user: null, unavailable: null }
  const { result } = event
  if (result.kind === 'user') return { user: result.user, unavailable: null }
  if (result.kind === 'anonymous') return { user: null, unavailable: null }
  if (state.user) return { user: state.user, unavailable: null }
  return { user: null, unavailable: result.message }
}

/** Only a refused session sends the user to the login page; a server that is down or silent does not. */
export async function loadSessionUser({
  getToken,
  refresh,
  getMe,
  timeoutMs = SESSION_BOOT_TIMEOUT_MS,
}: SessionBootDeps): Promise<SessionBootResult> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeout = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => reject(new SessionBootTimeout()), timeoutMs)
  })
  const load = async (): Promise<SessionBootResult> => {
    const token = getToken() ?? (await refresh())
    if (!token) return { kind: 'anonymous' }
    return { kind: 'user', user: await getMe() }
  }
  try {
    return await Promise.race([load(), timeout])
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return { kind: 'anonymous' }
    if (err instanceof ApiError && err.status !== 0) return { kind: 'unavailable', message: err.message }
    return { kind: 'unavailable', message: SERVER_UNAVAILABLE_MESSAGE }
  } finally {
    clearTimeout(timer)
  }
}
