import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { bootstrapMiniAppTheme } from '@/lib/theme'
import { initTelegramWebApp } from '@/tg-mini/lib/telegramWebAppInit'
import '@/styles/index.css'
import '@/tg-mini/styles/tg-mini.css'
import TgMiniApp from '@/tg-mini/App'

bootstrapMiniAppTheme()
initTelegramWebApp()

const boot = document.getElementById('tg-mini-boot')
if (boot) boot.remove()

const rootEl = document.getElementById('root')
if (rootEl) {
  createRoot(rootEl).render(
    <StrictMode>
      <TgMiniApp />
    </StrictMode>,
  )
}
