import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getFeatureModules } from '@/api/client'

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

export function FeatureModulesProvider({ children }: { children: React.ReactNode }) {
  const [features, setFeatures] = useState<Record<string, boolean>>({})
  const [frontendPaths, setFrontendPaths] = useState<Record<string, string>>({})
  const [settingsTabs, setSettingsTabs] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await getFeatureModules()
      setFeatures(data.features)
      setFrontendPaths(data.frontend_paths)
      setSettingsTabs(data.settings_tabs)
    } catch {
      setFeatures({})
      setFrontendPaths({})
      setSettingsTabs({})
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

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
