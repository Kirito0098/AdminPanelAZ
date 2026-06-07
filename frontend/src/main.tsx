import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { applyThemeClass, getStoredTheme } from './lib/theme'
import './styles/index.css'

applyThemeClass(getStoredTheme())

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
