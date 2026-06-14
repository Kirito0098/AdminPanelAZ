import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError } from '@/api/client'
import { clearTgToken, getTgSettings, getTgToken, setTgToken, tgAuth } from '@/tg-mini/api'
import type { TgMiniSettings } from '@/types'

type AuthStatus = 'loading' | 'authenticated' | 'error' | 'no-telegram'

interface TgAuthContextValue {
  status: AuthStatus
  error: string | null
  settings: TgMiniSettings | null
  isAdmin: boolean
  retryAuth: () => Promise<void>
  refreshSettings: () => Promise<void>
}

const TgAuthContext = createContext<TgAuthContextValue | null>(null)

function getWebApp() {
  return window.Telegram?.WebApp ?? null
}

export function TgAuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [error, setError] = useState<string | null>(null)
  const [settings, setSettings] = useState<TgMiniSettings | null>(null)

  const loadSettings = useCallback(async () => {
    const data = await getTgSettings()
    setSettings(data)
    return data
  }, [])

  const authenticate = useCallback(async () => {
    const tg = getWebApp()
    if (!tg?.initData) {
      setStatus('no-telegram')
      setError('Откройте приложение через Telegram')
      return
    }
    tg.ready()
    tg.expand()
    setStatus('loading')
    setError(null)
    try {
      const cached = getTgToken()
      if (!cached) {
        const auth = await tgAuth(tg.initData)
        setTgToken(auth.access_token)
      }
      await loadSettings()
      setStatus('authenticated')
    } catch (err) {
      clearTgToken()
      const message = err instanceof ApiError ? err.message : 'Ошибка авторизации'
      setError(message)
      setStatus('error')
    }
  }, [loadSettings])

  useEffect(() => {
    void authenticate()
  }, [authenticate])

  const value = useMemo(
    () => ({
      status,
      error,
      settings,
      isAdmin: settings?.role === 'admin',
      retryAuth: authenticate,
      refreshSettings: loadSettings,
    }),
    [authenticate, error, loadSettings, settings, status],
  )

  return <TgAuthContext.Provider value={value}>{children}</TgAuthContext.Provider>
}

export function useTgAuth() {
  const ctx = useContext(TgAuthContext)
  if (!ctx) throw new Error('useTgAuth must be used within TgAuthProvider')
  return ctx
}
