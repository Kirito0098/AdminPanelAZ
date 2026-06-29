export function applyThemeClass(theme: 'light' | 'dark') {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  localStorage.setItem('theme', theme)
}

export function getStoredTheme(): 'light' | 'dark' {
  const stored = localStorage.getItem('theme')
  if (stored === 'light' || stored === 'dark') return stored
  return 'dark'
}

export function normalizeTheme(value?: string | null): 'light' | 'dark' {
  return value === 'light' ? 'light' : 'dark'
}

/** Apply theme before React mounts in the Telegram Mini App WebView. */
export function bootstrapMiniAppTheme(): void {
  const tgScheme = window.Telegram?.WebApp?.colorScheme
  if (tgScheme === 'light' || tgScheme === 'dark') {
    applyThemeClass(tgScheme)
    return
  }
  applyThemeClass(getStoredTheme())
}
