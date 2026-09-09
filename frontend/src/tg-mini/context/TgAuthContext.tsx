import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '@/api/client'
import { isDocumentHidden } from '@/hooks/useIntervalWhenVisible'
import { applyThemeClass, normalizeTheme } from '@/lib/theme'
import {
  clearTgToken,
  getTgFeatureModules,
  getTgSettings,
  getTgToken,
  refreshTgSessionFromInitData,
} from '@/tg-mini/api'
import { initTelegramWebApp } from '@/tg-mini/lib/telegramWebAppInit'
import { getTelegramWebApp, TG_MINI_NO_INIT_DATA, waitForTelegramInitData } from '@/tg-mini/lib/telegramInitData'
import type { TgMiniSettings } from '@/types'

type AuthStatus = 'loading' | 'authenticated' | 'error' | 'no-telegram'

const FEATURE_REFRESH_RETRY_DELAY_MS = 3_000
const FEATURE_VISIBILITY_REFRESH_COOLDOWN_MS = 60_000

interface TgAuthContextValue {
  status: AuthStatus
  error: string | null
  settings: TgMiniSettings | null
  features: Record<string, boolean>
  featuresReady: boolean
  isAdmin: boolean
  retryAuth: () => Promise<void>
  refreshSettings: () => Promise<void>
  refreshFeatures: () => Promise<void>
}

const TgAuthContext = createContext<TgAuthContextValue | null>(null)

export function TgAuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [error, setError] = useState<string | null>(null)
  const [settings, setSettings] = useState<TgMiniSettings | null>(null)
  const [features, setFeatures] = useState<Record<string, boolean>>({})
  const [featuresReady, setFeaturesReady] = useState(false)
  const featureRetryTimeoutRef = useRef<number | null>(null)
  const lastFeatureAttemptAtRef = useRef(0)

  const loadSettings = useCallback(async (opts?: { retry?: boolean }) => {
    const data = await getTgSettings({ retry: opts?.retry ?? true })
    setSettings(data)
    applyThemeClass(normalizeTheme(data.theme))
    return data
  }, [])

  const clearFeatureRetry = useCallback(() => {
    if (featureRetryTimeoutRef.current === null) return
    window.clearTimeout(featureRetryTimeoutRef.current)
    featureRetryTimeoutRef.current = null
  }, [])

  const refreshFeatures = useCallback(async (opts?: { allowRetry?: boolean; markReadyOnSettle?: boolean }) => {
    if (opts?.allowRetry !== false) {
      clearFeatureRetry()
    }
    lastFeatureAttemptAtRef.current = Date.now()
    let scheduledRetry = false

    try {
      const data = await getTgFeatureModules()
      setFeatures(data.features || {})
    } catch {
      if (opts?.allowRetry !== false) {
        scheduledRetry = true
        featureRetryTimeoutRef.current = window.setTimeout(() => {
          featureRetryTimeoutRef.current = null
          void refreshFeatures({ allowRetry: false, markReadyOnSettle: opts?.markReadyOnSettle })
        }, FEATURE_REFRESH_RETRY_DELAY_MS)
      } else {
        setFeatures({})
      }
    } finally {
      if (opts?.markReadyOnSettle && !scheduledRetry) {
        setFeaturesReady(true)
      }
    }
  }, [clearFeatureRetry])

  const authenticate = useCallback(async () => {
    const tg = getTelegramWebApp()
    const initData = await waitForTelegramInitData(tg)
    if (!initData) {
      setStatus('no-telegram')
      setError(TG_MINI_NO_INIT_DATA)
      setFeatures({})
      setFeaturesReady(false)
      return
    }

    setStatus('loading')
    setError(null)

    try {
      // Do not auto-refresh on 401 here: tgFetch retry would call /auth, then we
      // would call /auth again below — duplicate "TG ID не привязан" notifies.
      if (getTgToken()) {
        try {
          // Authenticate as soon as settings succeed — features must not block Mini App.
          await loadSettings({ retry: false })
          setFeaturesReady(false)
          setStatus('authenticated')
          void refreshFeatures({ markReadyOnSettle: true })
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
      setFeaturesReady(false)
      setStatus('authenticated')
      void refreshFeatures({ markReadyOnSettle: true })
    } catch (err) {
      clearTgToken()
      const message = err instanceof ApiError ? err.message : 'Ошибка авторизации'
      setError(message)
      setFeatures({})
      setFeaturesReady(false)
      setStatus('error')
    }
  }, [loadSettings, refreshFeatures])

  useEffect(() => {
    initTelegramWebApp()
    void authenticate()
  }, [authenticate])

  useEffect(() => {
    if (status !== 'authenticated') return

    const onVisibilityChange = () => {
      if (isDocumentHidden()) return
      if (Date.now() - lastFeatureAttemptAtRef.current < FEATURE_VISIBILITY_REFRESH_COOLDOWN_MS) return
      void refreshFeatures()
    }

    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [refreshFeatures, status])

  useEffect(() => () => {
    clearFeatureRetry()
  }, [clearFeatureRetry])

  const refreshSettings = useCallback(async () => {
    await loadSettings()
  }, [loadSettings])

  const value = useMemo(
    () => ({
      status,
      error,
      settings,
      features,
      featuresReady,
      isAdmin: settings?.role === 'admin',
      retryAuth: authenticate,
      refreshSettings,
      refreshFeatures,
    }),
    [authenticate, error, features, featuresReady, refreshFeatures, refreshSettings, settings, status],
  )

  return <TgAuthContext.Provider value={value}>{children}</TgAuthContext.Provider>
}

export function useTgAuth() {
  const ctx = useContext(TgAuthContext)
  if (!ctx) throw new Error('useTgAuth must be used within TgAuthProvider')
  return ctx
}
