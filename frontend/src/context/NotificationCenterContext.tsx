import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchNotifications,
  markNotificationsRead,
  openNotificationsStream,
  setNotificationState,
  type NotificationCategory,
  type NotificationCounts,
  type NotificationItem,
  type NotificationLevel,
  type NotificationStatePatch,
} from '@/api/notifications'
import { useAuth } from '@/context/AuthContext'
import { useNotifications } from '@/context/NotificationContext'

export type NotificationTabKey = 'all' | NotificationCategory

export interface NotificationQuery {
  category: NotificationTabKey
  level: NotificationLevel | 'all'
  unreadOnly: boolean
  q: string
  hiddenOnly: boolean
}

export const DEFAULT_NOTIFICATION_QUERY: NotificationQuery = {
  category: 'all',
  level: 'all',
  unreadOnly: false,
  q: '',
  hiddenOnly: false,
}

export const EMPTY_NOTIFICATION_COUNTS: NotificationCounts = {
  unread: 0,
  attention: 0,
  snoozed: 0,
  hidden: 0,
  by_category: {},
}

const PAGE_SIZE = 50
const BELL_PREVIEW_LIMIT = 5

interface NotificationCenterValue {
  items: NotificationItem[]
  /** Только непрочитанные для колокола: свои параметры запроса, фильтры ленты на них не влияют. */
  bellItems: NotificationItem[]
  counts: NotificationCounts
  unreadCount: number
  pendingRequestsCount: number
  query: NotificationQuery
  setQuery: (patch: Partial<NotificationQuery>) => void
  loading: boolean
  hasMore: boolean
  refetch: () => Promise<void>
  loadMore: () => Promise<void>
  markAllRead: () => Promise<void>
  markReadUpTo: (id: number) => Promise<void>
  setState: (id: number, patch: NotificationStatePatch) => Promise<void>
}

const NotificationCenterContext = createContext<NotificationCenterValue | null>(null)

function snoozeToastKey(userId: number) {
  return `nc:snooze-notified:${userId}`
}

function readSnoozeSeen(userId: number): Set<number> {
  try {
    const raw = window.localStorage.getItem(snoozeToastKey(userId))
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    return new Set(
      Array.isArray(parsed) ? parsed.filter((value): value is number => typeof value === 'number') : [],
    )
  } catch {
    return new Set()
  }
}

function writeSnoozeSeen(userId: number, seen: Set<number>) {
  try {
    window.localStorage.setItem(snoozeToastKey(userId), JSON.stringify([...seen].slice(-200)))
  } catch {
    // приватный режим браузера: тост может повториться, данные не теряются
  }
}

export function NotificationCenterProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const { info, error: notifyError } = useNotifications()
  const isAdmin = user?.role === 'admin'
  const userId = user?.id ?? 0

  const [query, setQueryState] = useState<NotificationQuery>(DEFAULT_NOTIFICATION_QUERY)
  const [items, setItems] = useState<NotificationItem[]>([])
  const [bellItems, setBellItems] = useState<NotificationItem[]>([])
  const [counts, setCounts] = useState<NotificationCounts>(EMPTY_NOTIFICATION_COUNTS)
  const [pendingRequestsCount, setPendingRequestsCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(false)

  const queryRef = useRef<NotificationQuery>(DEFAULT_NOTIFICATION_QUERY)
  const prevPendingRef = useRef<number | null>(null)
  const bellGenerationRef = useRef(0)

  const buildParams = useCallback((beforeId?: number) => {
    const current = queryRef.current
    return {
      ...(current.category === 'all' ? {} : { category: current.category }),
      ...(current.level === 'all' ? {} : { level: current.level }),
      ...(current.unreadOnly ? { unread_only: true } : {}),
      ...(current.hiddenOnly ? { hidden_only: true } : {}),
      ...(current.q.trim() ? { q: current.q.trim() } : {}),
      ...(beforeId ? { before_id: beforeId } : {}),
      limit: PAGE_SIZE,
    }
  }, [])

  const notifySnoozedDue = useCallback(
    (next: NotificationItem[]) => {
      const now = Date.now()
      const seen = readSnoozeSeen(userId)
      const due = next.filter(
        (item) =>
          item.state.snoozed_until !== null &&
          Date.parse(item.state.snoozed_until) <= now &&
          !seen.has(item.id),
      )
      if (!due.length) return
      due.forEach((item) => {
        info(`Отложенное: ${item.title}`)
        seen.add(item.id)
      })
      writeSnoozeSeen(userId, seen)
    },
    [info, userId],
  )

  const refetch = useCallback(async () => {
    if (!isAdmin) return
    setLoading(true)
    try {
      const data = await fetchNotifications(buildParams())
      setItems(data.items)
      setCounts(data.counts)
      setHasMore(data.items.length >= PAGE_SIZE)
      setPendingRequestsCount(data.pending_requests_count)
      const prev = prevPendingRef.current
      if (prev != null && data.pending_requests_count > prev) {
        info(`Новых заявок на доступ: ${data.pending_requests_count - prev}`)
      }
      prevPendingRef.current = data.pending_requests_count
      notifySnoozedDue(data.items)
    } catch {
      notifyError('Не удалось загрузить уведомления')
    } finally {
      setLoading(false)
    }
  }, [buildParams, info, isAdmin, notifyError, notifySnoozedDue])

  const refetchBell = useCallback(async () => {
    if (!isAdmin) return
    // Колокол дёргают SSE, фокус и действия пользователя: ответы могут прийти в обратном
    // порядке, и устаревший не должен вернуть уже прочитанную карточку. counts живут
    // у refetch(), чтобы два параллельных запроса не писали счётчики вразнобой.
    const generation = ++bellGenerationRef.current
    try {
      const data = await fetchNotifications({ unread_only: true, limit: BELL_PREVIEW_LIMIT })
      if (generation === bellGenerationRef.current) setBellItems(data.items)
    } catch {
      // Колокол — вторичный список: при сбое остаются прошлые карточки, тост не поднимаем.
    }
  }, [isAdmin])

  const refetchAll = useCallback(async () => {
    await Promise.all([refetch(), refetchBell()])
  }, [refetch, refetchBell])

  const setQuery = useCallback((patch: Partial<NotificationQuery>) => {
    setQueryState((prev) => {
      const next = { ...prev, ...patch }
      queryRef.current = next
      return next
    })
  }, [])

  useEffect(() => {
    if (!isAdmin) return
    void refetch()
  }, [isAdmin, query, refetch])

  useEffect(() => {
    if (!isAdmin) return
    void refetchBell()
  }, [isAdmin, refetchBell])

  useEffect(() => {
    if (!isAdmin) return
    const stream = openNotificationsStream(() => void refetchAll())
    const onFocus = () => void refetchAll()
    window.addEventListener('focus', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
      stream.close()
    }
  }, [isAdmin, refetchAll])

  const loadMore = useCallback(async () => {
    if (!isAdmin || !items.length) return
    const lastId = items[items.length - 1].id
    try {
      const data = await fetchNotifications(buildParams(lastId))
      setItems((prev) => [...prev, ...data.items])
      setHasMore(data.items.length >= PAGE_SIZE)
      setCounts(data.counts)
    } catch {
      notifyError('Не удалось загрузить следующую страницу')
    }
  }, [buildParams, isAdmin, items, notifyError])


  const markAllRead = useCallback(async () => {
    if (!isAdmin) return
    try {
      const latest = await fetchNotifications({ limit: 1 })
      const topId = latest.items[0]?.id
      if (!topId) return
      await markNotificationsRead(topId)
    } catch {
      notifyError('Не удалось отметить уведомления прочитанными')
    } finally {
      await refetchAll()
    }
  }, [isAdmin, notifyError, refetchAll])

  const markReadUpTo = useCallback(
    async (id: number) => {
      if (!isAdmin || id < 1) return
      try {
        await markNotificationsRead(id)
      } catch {
        notifyError('Не удалось отметить уведомление прочитанным')
      } finally {
        await refetchAll()
      }
    },
    [isAdmin, notifyError, refetchAll],
  )

  const setState = useCallback(
    async (id: number, patch: NotificationStatePatch) => {
      if (!isAdmin) return
      try {
        await setNotificationState(id, patch)
      } catch {
        notifyError('Не удалось изменить состояние уведомления')
      } finally {
        await refetchAll()
      }
    },
    [isAdmin, notifyError, refetchAll],
  )

  const value = useMemo<NotificationCenterValue>(
    () => ({
      items,
      bellItems,
      counts,
      unreadCount: counts.unread,
      pendingRequestsCount,
      query,
      setQuery,
      loading,
      hasMore,
      refetch,
      loadMore,
      markAllRead,
      markReadUpTo,
      setState,
    }),
    [
      items,
      bellItems,
      counts,
      pendingRequestsCount,
      query,
      setQuery,
      loading,
      hasMore,
      refetch,
      loadMore,
      markAllRead,
      markReadUpTo,
      setState,
    ],
  )

  return (
    <NotificationCenterContext.Provider value={value}>{children}</NotificationCenterContext.Provider>
  )
}

export function useNotificationCenter(): NotificationCenterValue {
  const ctx = useContext(NotificationCenterContext)
  if (!ctx) {
    throw new Error('useNotificationCenter must be used within NotificationCenterProvider')
  }
  return ctx
}
