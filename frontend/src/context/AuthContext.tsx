import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from '@/api/client'
import { applyThemeClass, getStoredTheme } from '@/lib/theme'
import type { User } from '@/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const applyTheme = useCallback((theme: string) => {
    const t = theme === 'light' ? 'light' : 'dark'
    applyThemeClass(t)
  }, [])

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem('token')
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const me = await api.getMe()
      setUser(me)
      applyTheme(me.theme || getStoredTheme())
    } catch {
      localStorage.removeItem('token')
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [applyTheme])

  useEffect(() => {
    applyTheme(getStoredTheme())
    refreshUser()
  }, [applyTheme, refreshUser])

  const login = useCallback(
    async (username: string, password: string) => {
      const { access_token } = await api.login(username, password)
      localStorage.setItem('token', access_token)
      await refreshUser()
    },
    [refreshUser],
  )

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, logout, refreshUser }),
    [user, loading, login, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
