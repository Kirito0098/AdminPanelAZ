import { applyThemeClass } from '@/lib/theme'
import { getTelegramWebApp } from '@/tg-mini/lib/telegramInitData'

const THEME_PARAM_KEYS = [
  'bg_color',
  'text_color',
  'hint_color',
  'link_color',
  'button_color',
  'button_text_color',
  'secondary_bg_color',
] as const

function syncTelegramThemeParams(tg: NonNullable<ReturnType<typeof getTelegramWebApp>>): void {
  applyThemeClass(tg.colorScheme === 'light' ? 'light' : 'dark')

  const root = document.documentElement
  for (const key of THEME_PARAM_KEYS) {
    const value = tg.themeParams?.[key]
    root.style.setProperty(`--tg-theme-${key.replace(/_/g, '-')}`, value ?? '')
  }

  const mainButtonVisible = Boolean(tg.MainButton?.isVisible)
  root.style.setProperty('--tg-main-button-height', mainButtonVisible ? '3rem' : '0px')
  root.classList.toggle('tg-main-button-visible', mainButtonVisible)
}

export function initTelegramWebApp(): void {
  const tg = getTelegramWebApp()
  if (!tg) return

  tg.ready()
  tg.expand()
  syncTelegramThemeParams(tg)

  tg.onEvent('themeChanged', () => syncTelegramThemeParams(tg))
  tg.onEvent('viewportChanged', () => syncTelegramThemeParams(tg))
}
