import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError } from '@/api/client'
import { applyThemeClass, normalizeTheme } from '@/lib/theme'
import {
  clearTgToken,
  getTgSettings,
  getTgToken,
  refreshTgSessionFromInitData,
} from '@/tg-mini/api'
import { initTelegramWebApp } from '@/tg-mini/lib/telegramWebAppInit'
import { getTelegramWebApp, TG_MINI_NO_INIT_DATA, waitForTelegramInitData } from '@/tg-mini/lib/telegramInitData'
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

export function TgAuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [error, setError] = useState<string | null>(null)
  const [settings, setSettings] = useState<TgMiniSettings | null>(null)

  const loadSettings = useCallback(async (opts?: { retry?: boolean }) => {
    const data = await getTgSettings({ retry: opts?.retry ?? true })
    setSettings(data)
    applyThemeClass(normalizeTheme(data.theme))
    return data
  }, [])

  const authenticate = useCallback(async () => {
    const tg = getTelegramWebApp()
    const initData = await waitForTelegramInitData(tg)
    if (!initData) {
      setStatus('no-telegram')
      setError(TG_MINI_NO_INIT_DATA)
      return
    }

    setStatus('loading')
    setError(null)

    try {
      // Do not auto-refresh on 401 here: tgFetch retry would call /auth, then we
      // would call /auth again below — duplicate "TG ID не привязан" notifies.
      if (getTgToken()) {
        try {
          await loadSettings({ retry: false })
          setStatus('authenticated')
          return
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 401)) {
            throw err
          }
          clearTgToken()
        }
      }

      await refreshTgSessionFromInitData(initData)
      await loadSettings({ retry: false })
      setStatus('authenticated')
    } catch (err) {
      clearTgToken()
      const message = err instanceof ApiError ? err.message : 'Ошибка авторизации'
      setError(message)
      setStatus('error')
    }
  }, [loadSettings])

  useEffect(() => {
    initTelegramWebApp()
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
