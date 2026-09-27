export const TG_ERROR_MAX_LENGTH = 300

const WEB_SESSION_ID_RE = /^[A-Za-z0-9_-]{1,64}$/

export interface LoginRedirectParams {
  token: string | null
  webSessionId: string | null
  tgError: string | null
}

function safeDecodeURIComponent(raw: string): string {
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
}

function readHashParams(hash: string): Map<string, string> {
  const params = new Map<string, string>()
  if (!hash.startsWith('#')) return params
  for (const part of hash.slice(1).split('&')) {
    const eq = part.indexOf('=')
    if (eq > 0) params.set(part.slice(0, eq), safeDecodeURIComponent(part.slice(eq + 1)))
  }
  return params
}

/**
 * Token, web session id and Telegram login error the server appends to /login. URLSearchParams
 * already decodes query values; only the hash values are still percent-encoded.
 */
export function readLoginRedirectParams(hash: string, search: URLSearchParams): LoginRedirectParams {
  const hashParams = readHashParams(hash)
  const hashToken = hashParams.get('token') || null
  const token = hashToken ?? (search.get('token') || null)
  const session = hashParams.get('session') ?? ''
  const webSessionId = hashToken && WEB_SESSION_ID_RE.test(session) ? session : null
  const tgError = (search.get('tg_error') || '').trim().slice(0, TG_ERROR_MAX_LENGTH)
  return { token, webSessionId, tgError: tgError || null }
}
