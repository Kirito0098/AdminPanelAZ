declare global {
  interface Window {
    __webpack_nonce__?: string
  }
}

/** Share CSP nonce with libraries that inject <style> tags (Radix scroll lock, etc.). */
export function initCspNonce(): void {
  const fromScript = document.querySelector('script[nonce]')?.getAttribute('nonce')
  const fromMeta = document.querySelector('meta[name="csp-nonce"]')?.getAttribute('content')
  const nonce = fromScript || fromMeta || undefined
  if (!nonce) return
  window.__webpack_nonce__ = nonce
}
