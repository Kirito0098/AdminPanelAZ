/** In-memory access JWT — never persisted to localStorage (XSS-resistant). */

let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function clearAccessToken(): void {
  accessToken = null
}

/** One-shot migration: drop legacy localStorage token after moving to memory. */
export function migrateLegacyAccessToken(): string | null {
  try {
    const legacy = localStorage.getItem('token')
    if (legacy) {
      localStorage.removeItem('token')
      if (!accessToken) accessToken = legacy
      return accessToken
    }
  } catch {
    /* ignore storage errors */
  }
  return accessToken
}
