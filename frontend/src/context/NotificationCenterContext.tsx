import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchNotifications,
  markNotificationsRead,
  openNotificationsStream,
  type NotificationItem,
} from '@/api/notifications'
import { useAuth } from '@/context/AuthContext'
import { useNotifications } from '@/context/NotificationContext'

export type NotificationTabKey =
  | 'all'
  | 'requests'
  | 'security'
  | 'nodes'
  | 'services'
  | 'tasks'

interface NotificationCenterValue {
  items: NotificationItem[]
  unreadCount: number
  pendingRequestsCount: number
  category: NotificationTabKey
  setCategory: (category: NotificationTabKey) => void
  refetch: () => Promise<void>
  /** Отметить прочитанным всё, что есть в ленте (включая скрытое фильтром вкладки). */
  markAllRead: () => Promise<void>
  /** Отметить прочитанным конкретное уведомление и всё, что старше него. */
  markReadUpTo: (id: number) => Promise<void>
}

const NotificationCenterContext = createContext<NotificationCenterValue | null>(null)

/**
 * Единый владелец ленты уведомлений и SSE-потока.
 *
 * Раньше колокол и бейдж сайдбара тянули данные независимо, поэтому счётчик
 * заявок в сайдбаре «застывал» до перезагрузки страницы. Теперь один поток
 * обновляет и колокол, и навигацию.
 */
export function NotificationCenterProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const { info } = useNotifications()
  const isAdmin = user?.role === 'admin'

  const [category, setCategoryState] = useState<NotificationTabKey>('all')
  const [items, setItems] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [pendingRequestsCount, setPendingRequestsCount] = useState(0)
  // Категория нужна внутри refetch без пересоздания SSE-подключения.
  const categoryRef = useRef<NotificationTabKey>('all')
  /** null = ещё не было успешного fetch; тост только при реальном росте после baseline. */
  const prevPendingRef = useRef<number | null>(null)

  const refetch = useCallback(async () => {
    if (!isAdmin) return
    try {
      const data = await fetchNotifications({
        ...(categoryRef.current === 'all' ? {} : { category: categoryRef.current }),
        limit: 100,
      })
      setItems(data.items)
      setUnreadCount(data.unread_count)
      const pending = data.pending_requests_count
      setPendingRequestsCount(pending)
      const prev = prevPendingRef.current
      if (
        prev != null &&
        pending > prev &&
        (categoryRef.current === 'all' || categoryRef.current === 'requests')
      ) {
        info(`Новых заявок на доступ: ${pending - prev}`)
      }
      prevPendingRef.current = pending
    } catch {
      // Оставляем прежние данные: SSE переподключится и вызовет refetch.
    }
  }, [info, isAdmin])

  const setCategory = useCallback(
    (next: NotificationTabKey) => {
      categoryRef.current = next
      setCategoryState(next)
      void refetch()
    },
    [refetch],
  )

  useEffect(() => {
    if (!isAdmin) return
    void refetch()
    const stream = openNotificationsStream(() => {
      void refetch()
    })
    const onFocus = () => void refetch()
    window.addEventListener('focus', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
      stream.close()
    }
  }, [isAdmin, refetch])

  const markAllRead = useCallback(async () => {
    if (!isAdmin) return
    try {
      // Верхний id берём без фильтра вкладки — иначе непрочитанное в других
      // категориях остаётся в бейдже после «Отметить всё как прочитанное».
      const latest = await fetchNotifications({ limit: 1 })
      const topId = latest.items[0]?.id
      if (!topId) return
      await markNotificationsRead(topId)
      setUnreadCount(0)
    } catch {
      // Счётчик не обнуляем: следующий refetch покажет реальное состояние.
    } finally {
      await refetch()
    }
  }, [isAdmin, refetch])

  const markReadUpTo = useCallback(
    async (id: number) => {
      if (!isAdmin || id < 1) return
      try {
        await markNotificationsRead(id)
      } catch {
        // Счётчик не критичен: следующий refetch покажет реальное состояние.
      } finally {
        await refetch()
      }
    },
    [isAdmin, refetch],
  )

  const value = useMemo<NotificationCenterValue>(
    () => ({
      items,
      unreadCount,
      pendingRequestsCount,
      category,
      setCategory,
      refetch,
      markAllRead,
      markReadUpTo,
    }),
    [
      items,
      unreadCount,
      pendingRequestsCount,
      category,
      setCategory,
      refetch,
      markAllRead,
      markReadUpTo,
    ],
  )

  return (
    <NotificationCenterContext.Provider value={value}>
      {children}
    </NotificationCenterContext.Provider>
  )
}

export function useNotificationCenter(): NotificationCenterValue {
  const ctx = useContext(NotificationCenterContext)
  if (!ctx) {
    throw new Error('useNotificationCenter must be used within NotificationCenterProvider')
  }
  return ctx
}
