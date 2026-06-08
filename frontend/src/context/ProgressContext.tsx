import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import BackgroundTaskProgress from '@/components/ui/BackgroundTaskProgress'
import { GlobalProgressBar, InlineProgressBar } from '@/components/ui/ProgressBar'
import { useBackgroundTaskPoll, type BackgroundTaskPollOptions } from '@/hooks/useBackgroundTaskPoll'
import type { BackgroundTask } from '@/types'

interface InlineProgress {
  active: boolean
  label?: string
}

interface TrackBackgroundTaskOptions extends BackgroundTaskPollOptions {
  okMessage?: string
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
  backgroundTask: BackgroundTask | null
  backgroundTaskPolling: boolean
  trackBackgroundTask: (taskId: string, options?: TrackBackgroundTaskOptions) => void
  stopBackgroundTask: () => void
}

const ProgressContext = createContext<ProgressContextValue | null>(null)

export function ProgressProvider({ children }: { children: React.ReactNode }) {
  const [globalActive, setGlobalActive] = useState(false)
  const [inline, setInline] = useState<InlineProgress>({ active: false })
  const globalCountRef = useRef(0)
  const callbacksRef = useRef<TrackBackgroundTaskOptions>({})
  const { task: backgroundTask, polling: backgroundTaskPolling, startPoll, stopPoll } = useBackgroundTaskPoll()

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

  const stopBackgroundTask = useCallback(() => {
    stopPoll()
  }, [stopPoll])

  const trackBackgroundTask = useCallback(
    (taskId: string, options: TrackBackgroundTaskOptions = {}) => {
      callbacksRef.current = options
      startPoll(taskId, {
        ...options,
        onComplete: (task) => {
          options.onComplete?.(task)
        },
        onError: (task, message) => {
          options.onError?.(task, message)
        },
      })
    },
    [startPoll],
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
      backgroundTask,
      backgroundTaskPolling,
      trackBackgroundTask,
      stopBackgroundTask,
    }),
    [
      globalActive,
      startGlobal,
      doneGlobal,
      inline,
      startInline,
      doneInline,
      withGlobal,
      withInline,
      backgroundTask,
      backgroundTaskPolling,
      trackBackgroundTask,
      stopBackgroundTask,
    ],
  )

  return (
    <ProgressContext.Provider value={value}>
      <GlobalProgressBar active={globalActive} />
      <BackgroundTaskProgress task={backgroundTask} />
      {children}
    </ProgressContext.Provider>
  )
}

export function useProgress() {
  const ctx = useContext(ProgressContext)
  if (!ctx) throw new Error('useProgress must be used within ProgressProvider')
  return ctx
}
