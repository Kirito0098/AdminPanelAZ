import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { initCspNonce } from './lib/cspNonce'
import { applyThemeClass, getStoredTheme } from './lib/theme'
import './styles/index.css'

initCspNonce()
applyThemeClass(getStoredTheme())

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
