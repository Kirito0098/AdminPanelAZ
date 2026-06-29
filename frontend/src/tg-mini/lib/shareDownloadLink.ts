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

export function openExternalLink(url: string): void {
  window.Telegram?.WebApp?.openLink(url)
}
