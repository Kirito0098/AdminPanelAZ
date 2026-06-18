import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { updateSettings } from '@/api/client'
import { getBrowserTimeZone, getTimeZoneLabel, setActiveTimeZone } from '@/lib/datetime'
import { useAuth } from './AuthContext'

interface TimezoneOption {
  value: string
  label: string
}

interface TimezoneContextValue {
  /** User selected timezone, '' means follow the browser. */
  timeZone: string
  /** Timezone actually used for rendering (resolves '' to the browser zone). */
  effectiveTimeZone: string
  browserTimeZone: string
  options: TimezoneOption[]
  setTimeZone: (tz: string) => Promise<void>
}

const TimezoneContext = createContext<TimezoneContextValue | null>(null)

const COMMON_ZONES = [
  'UTC',
  'Europe/Kaliningrad',
  'Europe/Moscow',
  'Europe/Kiev',
  'Europe/Minsk',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Istanbul',
  'Asia/Yerevan',
  'Asia/Tbilisi',
  'Asia/Baku',
  'Asia/Almaty',
  'Asia/Tashkent',
  'Asia/Yekaterinburg',
  'Asia/Novosibirsk',
  'Asia/Krasnoyarsk',
  'Asia/Irkutsk',
  'Asia/Yakutsk',
  'Asia/Vladivostok',
  'Asia/Dubai',
  'Asia/Tehran',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'America/New_York',
  'America/Chicago',
  'America/Los_Angeles',
]

export function TimezoneProvider({ children }: { children: React.ReactNode }) {
  const { user, refreshUser } = useAuth()
  const browserTimeZone = useMemo(() => getBrowserTimeZone(), [])
  const [timeZone, setTimeZoneState] = useState<string>('')

  useEffect(() => {
    const tz = user?.timezone ?? ''
    setTimeZoneState(tz)
    setActiveTimeZone(tz)
  }, [user?.timezone])

  const setTimeZone = useCallback(
    async (tz: string) => {
      const value = (tz || '').trim()
      setTimeZoneState(value)
      setActiveTimeZone(value)
      if (user) {
        try {
          await updateSettings({ timezone: value })
          await refreshUser()
        } catch {
          /* local timezone still applied */
        }
      }
    },
    [user, refreshUser],
  )

  const options = useMemo<TimezoneOption[]>(() => {
    const zones = new Set<string>(COMMON_ZONES)
    if (browserTimeZone) zones.add(browserTimeZone)
    return Array.from(zones)
      .map((value) => ({ value, label: `${value} (${getTimeZoneLabel(value)})` }))
      .sort((a, b) => a.label.localeCompare(b.label, 'ru'))
  }, [browserTimeZone])

  const value = useMemo<TimezoneContextValue>(
    () => ({
      timeZone,
      effectiveTimeZone: timeZone || browserTimeZone,
      browserTimeZone,
      options,
      setTimeZone,
    }),
    [timeZone, browserTimeZone, options, setTimeZone],
  )

  return <TimezoneContext.Provider value={value}>{children}</TimezoneContext.Provider>
}

export function useTimezone() {
  const ctx = useContext(TimezoneContext)
  if (!ctx) throw new Error('useTimezone must be used within TimezoneProvider')
  return ctx
}
