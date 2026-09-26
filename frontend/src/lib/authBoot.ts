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
