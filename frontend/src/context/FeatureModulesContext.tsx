import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getFeatureModules } from '@/api/client'
import { useAuth } from '@/context/AuthContext'

interface FeatureModulesContextValue {
  features: Record<string, boolean>
  frontendPaths: Record<string, string>
  settingsTabs: Record<string, string>
  loading: boolean
  isEnabled: (key: string) => boolean
  isPathEnabled: (path: string) => boolean
  isSettingsTabEnabled: (tab: string) => boolean
  refresh: () => Promise<void>
}

const FeatureModulesContext = createContext<FeatureModulesContextValue | null>(null)

// Кэш последнего успешного ответа: сайдбар не должен на несколько секунд показывать
// отключённые разделы (или пустеть) до завершения /feature-modules.
const CACHE_KEY = 'adminpanelaz:feature-modules:v1'

type FeatureModulesPayload = {
  features: Record<string, boolean>
  frontendPaths: Record<string, string>
  settingsTabs: Record<string, string>
}

function readCachedModules(): FeatureModulesPayload | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<FeatureModulesPayload> | null
    if (!parsed || typeof parsed.features !== 'object' || !parsed.features) return null
    return {
      features: parsed.features,
      frontendPaths: parsed.frontendPaths ?? {},
      settingsTabs: parsed.settingsTabs ?? {},
    }
  } catch {
    return null
  }
}

function writeCachedModules(payload: FeatureModulesPayload) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(payload))
  } catch {
    // Приватный режим/переполнение — работаем без кэша.
  }
}

function clearCachedModules() {
  try {
    localStorage.removeItem(CACHE_KEY)
  } catch {
    // ignore
  }
}

export function FeatureModulesProvider({ children }: { children: React.ReactNode }) {
  const [features, setFeatures] = useState<Record<string, boolean>>(
    () => readCachedModules()?.features ?? {},
  )
  const [frontendPaths, setFrontendPaths] = useState<Record<string, string>>(
    () => readCachedModules()?.frontendPaths ?? {},
  )
  const [settingsTabs, setSettingsTabs] = useState<Record<string, string>>(
    () => readCachedModules()?.settingsTabs ?? {},
  )
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await getFeatureModules()
      setFeatures(data.features)
      setFrontendPaths(data.frontend_paths)
      setSettingsTabs(data.settings_tabs)
      writeCachedModules({
        features: data.features,
        frontendPaths: data.frontend_paths,
        settingsTabs: data.settings_tabs,
      })
    } catch {
      // Оставляем кэш/текущее состояние: сброс в {} включил бы все модули.
    } finally {
      setLoading(false)
    }
  }, [])

  const username = useAuth().user?.username
  useEffect(() => {
    if (username) {
      refresh()
      return
    }
    clearCachedModules()
    setFeatures({})
    setFrontendPaths({})
    setSettingsTabs({})
    setLoading(false)
  }, [username, refresh])

  const isEnabled = useCallback(
    (key: string) => features[key] ?? true,
    [features],
  )

  const isPathEnabled = useCallback(
    (path: string) => {
      const key = frontendPaths[path]
      return key ? isEnabled(key) : true
    },
    [frontendPaths, isEnabled],
  )

  const isSettingsTabEnabled = useCallback(
    (tab: string) => {
      const key = settingsTabs[tab]
      return key ? isEnabled(key) : true
    },
    [settingsTabs, isEnabled],
  )

  const value = useMemo(
    () => ({
      features,
      frontendPaths,
      settingsTabs,
      loading,
      isEnabled,
      isPathEnabled,
      isSettingsTabEnabled,
      refresh,
    }),
    [features, frontendPaths, settingsTabs, loading, isEnabled, isPathEnabled, isSettingsTabEnabled, refresh],
  )

  return <FeatureModulesContext.Provider value={value}>{children}</FeatureModulesContext.Provider>
}

export function useFeatureModules() {
  const ctx = useContext(FeatureModulesContext)
  if (!ctx) throw new Error('useFeatureModules must be used within FeatureModulesProvider')
  return ctx
}
