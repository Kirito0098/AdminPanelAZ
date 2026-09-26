import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import * as api from '@/api/client'
import { refreshAccessToken } from '@/api/http'
import { useSessionHeartbeat } from '@/hooks/useSessionHeartbeat'
import { clearAccessToken, getAccessToken, migrateLegacyAccessToken, setAccessToken } from '@/lib/accessToken'
import { loadSessionUser } from '@/lib/authBoot'
import { onSessionLost } from '@/lib/sessionLost'
import { setActiveTimeZone } from '@/lib/datetime'
import { applyThemeClass, getStoredTheme } from '@/lib/theme'
import { storeWebSessionId } from '@/lib/webSession'
import type { User } from '@/types'

const REFRESH_INTERVAL_MS = 25 * 60 * 1000

interface AuthContextValue {
  user: User | null
  loading: boolean
  /** Why the session could not be checked (server down or silent); null when it was. */
  unavailable: string | null
  retry: () => Promise<void>
  /** The server refused to renew a signed-in session; the login page explains why the user is there. */
  sessionEnded: boolean
  login: (username: string, password: string) => Promise<api.LoginResult>
  setToken: (token: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState<string | null>(null)
  const [sessionEnded, setSessionEnded] = useState(false)
  const userRef = useRef<User | null>(null)
  userRef.current = user
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const applyTheme = useCallback((theme: string) => {
    const t = theme === 'light' ? 'light' : 'dark'
    applyThemeClass(t)
  }, [])

  const refreshUser = useCallback(async () => {
    migrateLegacyAccessToken()
    const result = await loadSessionUser({
      getToken: getAccessToken,
      refresh: refreshAccessToken,
      getMe: api.getMe,
    })
    if (result.kind === 'user') {
      setUser(result.user)
      setUnavailable(null)
      setSessionEnded(false)
      applyTheme(result.user.theme || getStoredTheme())
      setActiveTimeZone(result.user.timezone || '')
    } else if (result.kind === 'anonymous') {
      clearAccessToken()
      setUser(null)
      setUnavailable(null)
    } else {
      setUnavailable(result.message)
    }
    setLoading(false)
  }, [applyTheme])

  const retry = useCallback(async () => {
    setLoading(true)
    await refreshUser()
  }, [refreshUser])

  const silentRefresh = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return
    try {
      // Shared mutex with apiFetch. A refused session is reported through onSessionLost.
      // Network and server errors reject without clearing; keep the session for retry.
      await refreshAccessToken()
    } catch {
      /* ignore background network errors — access token kept */
    }
  }, [])

  useEffect(() => {
    applyTheme(getStoredTheme())
    void refreshUser()
  }, [applyTheme, refreshUser])

  useEffect(() => {
    if (!user) {
      if (refreshTimer.current) {
        clearInterval(refreshTimer.current)
        refreshTimer.current = null
      }
      return
    }
    refreshTimer.current = setInterval(silentRefresh, REFRESH_INTERVAL_MS)
    const onVisible = () => {
      if (document.hidden) return
      void silentRefresh()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      if (refreshTimer.current) clearInterval(refreshTimer.current)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [user, silentRefresh])

  const logout = useCallback(() => {
    api.logoutApi().catch(() => {})
    clearAccessToken()
    try {
      localStorage.removeItem('token')
    } catch {
      /* ignore */
    }
    setUser(null)
    setUnavailable(null)
  }, [])

  useEffect(
    () =>
      onSessionLost(() => {
        if (!userRef.current) return
        setSessionEnded(true)
        setUser(null)
      }),
    [],
  )

  const endRevokedSession = useCallback(() => {
    setSessionEnded(true)
    logout()
  }, [logout])

  useSessionHeartbeat(!!user, endRevokedSession)

  const login = useCallback(async (username: string, password: string) => {
    const result = await api.login(username, password)
    if ('access_token' in result && result.access_token) {
      setAccessToken(result.access_token)
      if (result.web_session_id) {
        storeWebSessionId(result.web_session_id)
      }
      await refreshUser()
    }
    return result
  }, [refreshUser])

  const setToken = useCallback(
    async (token: string) => {
      setAccessToken(token)
      await refreshUser()
    },
    [refreshUser],
  )

  const value = useMemo(
    () => ({ user, loading, unavailable, retry, sessionEnded, login, setToken, logout, refreshUser }),
    [user, loading, unavailable, retry, sessionEnded, login, setToken, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
