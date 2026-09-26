export const TG_ERROR_MAX_LENGTH = 300

export interface LoginRedirectParams {
  token: string | null
  tgError: string | null
}

function safeDecodeURIComponent(raw: string): string {
  try {
    return decodeURIComponent(raw)
  } catch {
    return raw
  }
}

/**
 * Token and Telegram login error the server appends to /login. URLSearchParams already
 * decodes query values; only the hash token is still percent-encoded.
 */
export function readLoginRedirectParams(hash: string, search: URLSearchParams): LoginRedirectParams {
  const hashToken = hash.match(/^#token=(.+)$/)?.[1]
  const token = hashToken ? safeDecodeURIComponent(hashToken) : search.get('token') || null
  const tgError = (search.get('tg_error') || '').trim().slice(0, TG_ERROR_MAX_LENGTH)
  return { token, tgError: tgError || null }
}
