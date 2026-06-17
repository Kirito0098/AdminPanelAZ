declare global {
  interface Window {
    __webpack_nonce__?: string
  }
}

let cachedNonce: string | undefined

/** CSP nonce from the served HTML (script tag or meta). */
export function getCspNonce(): string | undefined {
  if (cachedNonce !== undefined) {
    return cachedNonce || undefined
  }
  const fromScript = document.querySelector('script[nonce]')?.getAttribute('nonce')
  const fromMeta = document.querySelector('meta[name="csp-nonce"]')?.getAttribute('content')
  cachedNonce = fromScript || fromMeta || ''
  return cachedNonce || undefined
}

/** Share CSP nonce with libraries that inject <style> tags (Radix scroll lock, etc.). */
export function initCspNonce(): void {
  const nonce = getCspNonce()
  if (!nonce) return
  window.__webpack_nonce__ = nonce
}
