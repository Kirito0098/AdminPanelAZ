export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/** Native Telegram share sheet — does not open the URL. */
export function shareViaTelegram(url: string, text = 'Ссылка на VPN-конфиг'): boolean {
  const shareUrl = window.Telegram?.WebApp?.shareUrl
  if (typeof shareUrl === 'function') {
    shareUrl(url, text)
    return true
  }
  return false
}

/** Открыть внешнюю ссылку: в Mini App — средствами Telegram, в браузере — новым окном. */
export function openExternalLink(url: string): void {
  const webApp = window.Telegram?.WebApp
  // t.me-ссылки открываем внутри Telegram: обычный <a target="_blank"> в WebView не срабатывает.
  if (webApp?.openTelegramLink && /^https:\/\/t\.me\//i.test(url)) {
    webApp.openTelegramLink(url)
    return
  }
  if (webApp?.openLink) {
    webApp.openLink(url)
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}
