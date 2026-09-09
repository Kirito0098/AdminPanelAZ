import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import * as api from '@/api/client'
import { refreshAccessToken } from '@/api/http'
import { useSessionHeartbeat } from '@/hooks/useSessionHeartbeat'
import { clearAccessToken, getAccessToken, migrateLegacyAccessToken, setAccessToken } from '@/lib/accessToken'
import { setActiveTimeZone } from '@/lib/datetime'
import { applyThemeClass, getStoredTheme } from '@/lib/theme'
import { storeWebSessionId } from '@/lib/webSession'
import type { User } from '@/types'

const REFRESH_INTERVAL_MS = 25 * 60 * 1000

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<api.LoginResult>
  setToken: (token: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const applyTheme = useCallback((theme: string) => {
    const t = theme === 'light' ? 'light' : 'dark'
    applyThemeClass(t)
  }, [])

  const refreshUser = useCallback(async () => {
    migrateLegacyAccessToken()
    let token = getAccessToken()
    if (!token) {
      token = await refreshAccessToken()
    }
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const me = await api.getMe()
      setUser(me)
      applyTheme(me.theme || getStoredTheme())
      setActiveTimeZone(me.timezone || '')
    } catch {
      clearAccessToken()
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [applyTheme])

  const silentRefresh = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return
    try {
      await refreshAccessToken()
    } catch {
      /* ignore background refresh errors */
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
  }, [])

  useSessionHeartbeat(!!user, logout)

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
    () => ({ user, loading, login, setToken, logout, refreshUser }),
    [user, loading, login, setToken, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
