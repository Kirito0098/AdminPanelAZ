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
