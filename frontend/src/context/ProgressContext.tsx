import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { GlobalProgressBar, InlineProgressBar } from '@/components/ui/ProgressBar'

interface InlineProgress {
  active: boolean
  label?: string
}

interface ProgressContextValue {
  globalActive: boolean
  startGlobal: () => void
  doneGlobal: () => void
  inline: InlineProgress
  startInline: (label?: string) => void
  doneInline: () => void
  withGlobal: <T>(fn: () => Promise<T>) => Promise<T>
  withInline: <T>(fn: () => Promise<T>, label?: string) => Promise<T>
}

const ProgressContext = createContext<ProgressContextValue | null>(null)

export function ProgressProvider({ children }: { children: React.ReactNode }) {
  const [globalActive, setGlobalActive] = useState(false)
  const [inline, setInline] = useState<InlineProgress>({ active: false })
  const globalCountRef = useRef(0)

  const startGlobal = useCallback(() => {
    globalCountRef.current += 1
    setGlobalActive(true)
  }, [])

  const doneGlobal = useCallback(() => {
    globalCountRef.current = Math.max(0, globalCountRef.current - 1)
    if (globalCountRef.current === 0) {
      setGlobalActive(false)
    }
  }, [])

  const startInline = useCallback((label?: string) => {
    setInline({ active: true, label })
  }, [])

  const doneInline = useCallback(() => {
    setInline({ active: false })
  }, [])

  const withGlobal = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T> => {
      startGlobal()
      try {
        return await fn()
      } finally {
        doneGlobal()
      }
    },
    [startGlobal, doneGlobal],
  )

  const withInline = useCallback(
    async <T,>(fn: () => Promise<T>, label?: string): Promise<T> => {
      startInline(label)
      try {
        return await fn()
      } finally {
        doneInline()
      }
    },
    [startInline, doneInline],
  )

  const value = useMemo(
    () => ({
      globalActive,
      startGlobal,
      doneGlobal,
      inline,
      startInline,
      doneInline,
      withGlobal,
      withInline,
    }),
    [globalActive, startGlobal, doneGlobal, inline, startInline, doneInline, withGlobal, withInline],
  )

  return (
    <ProgressContext.Provider value={value}>
      <GlobalProgressBar active={globalActive} />
      {children}
    </ProgressContext.Provider>
  )
}

export function useProgress() {
  const ctx = useContext(ProgressContext)
  if (!ctx) throw new Error('useProgress must be used within ProgressProvider')
  return ctx
}
