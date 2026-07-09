import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import Toast from '@/components/ui/Toast'
import { randomId } from '@/lib/randomId'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: string
  type: ToastType
  message: string
  duration: number
}

interface NotificationContextValue {
  notify: (type: ToastType, message: string, duration?: number) => string
  success: (message: string) => string
  error: (message: string) => string
  warning: (message: string) => string
  info: (message: string) => string
  dismiss: (id: string) => void
}

const DEFAULT_DURATION = 4500

const NotificationContext = createContext<NotificationContextValue | null>(null)

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const recentErrorsRef = useRef<Map<string, number>>(new Map())
  const ERROR_DEDUP_MS = 5000

  const dismiss = useCallback((id: string) => {
    const timer = timersRef.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timersRef.current.delete(id)
    }
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const notify = useCallback(
    (type: ToastType, message: string, duration = DEFAULT_DURATION) => {
      const id = randomId()
      setToasts((prev) => [...prev, { id, type, message, duration }])

      const timer = setTimeout(() => dismiss(id), duration)
      timersRef.current.set(id, timer)

      return id
    },
    [dismiss],
  )

  const success = useCallback((message: string) => notify('success', message), [notify])
  const error = useCallback(
    (message: string) => {
      const now = Date.now()
      const lastShown = recentErrorsRef.current.get(message)
      if (lastShown != null && now - lastShown < ERROR_DEDUP_MS) {
        return ''
      }
      recentErrorsRef.current.set(message, now)
      if (recentErrorsRef.current.size > 32) {
        for (const [key, ts] of recentErrorsRef.current) {
          if (now - ts > ERROR_DEDUP_MS) recentErrorsRef.current.delete(key)
        }
      }
      return notify('error', message)
    },
    [notify],
  )
  const warning = useCallback((message: string) => notify('warning', message), [notify])
  const info = useCallback((message: string) => notify('info', message), [notify])

  const value = useMemo(
    () => ({ notify, success, error, warning, info, dismiss }),
    [notify, success, error, warning, info, dismiss],
  )

  return (
    <NotificationContext.Provider value={value}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[100] flex max-h-[min(80vh,32rem)] flex-col-reverse gap-2 overflow-hidden pointer-events-none sm:max-w-sm"
        aria-live="polite"
        aria-relevant="additions"
      >
        {toasts.map((toast) => (
          <Toast key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </NotificationContext.Provider>
  )
}

export function useNotifications() {
  const ctx = useContext(NotificationContext)
  if (!ctx) throw new Error('useNotifications must be used within NotificationProvider')
  return ctx
}
