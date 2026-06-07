import React, { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { updateSettings } from '../api/client'
import { useAuth } from './AuthContext'

interface ThemeContextValue {
  theme: 'light' | 'dark'
  toggleTheme: () => Promise<void>
  setTheme: (theme: 'light' | 'dark') => Promise<void>
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { user, refreshUser } = useAuth()
  const [theme, setThemeState] = useState<'light' | 'dark'>(
    () => (localStorage.getItem('theme') as 'light' | 'dark') || 'dark',
  )

  const apply = useCallback((t: 'light' | 'dark') => {
    document.documentElement.setAttribute('data-theme', t)
    localStorage.setItem('theme', t)
    setThemeState(t)
  }, [])

  const setTheme = useCallback(async (t: 'light' | 'dark') => {
    apply(t)
    if (user) {
      try {
        await updateSettings({ theme: t })
        await refreshUser()
      } catch {
        /* local theme still applied */
      }
    }
  }, [apply, user, refreshUser])

  const toggleTheme = useCallback(async () => {
    await setTheme(theme === 'dark' ? 'light' : 'dark')
  }, [setTheme, theme])

  const value = useMemo(() => ({ theme, toggleTheme, setTheme }), [theme, toggleTheme, setTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
