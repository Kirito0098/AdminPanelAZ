import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@/styles/index.css'
import '@/tg-mini/styles/tg-mini.css'
import TgMiniApp from '@/tg-mini/App'

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
