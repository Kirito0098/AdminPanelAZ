import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { ApiError, getUsers } from '@/api/client'
import { USERS_FILTER_IDS, type StaleFilter } from '@/components/users/UsersFilters'
import { useNotifications } from '@/context/NotificationContext'
import { parseTimestamp } from '@/lib/datetime'
import {
  loadPageSize,
  loadUsersListPrefs,
  savePageSize,
  saveUsersListPrefs,
  type UsersSortDir,
  type UsersSortKey,
} from '@/lib/usersListPrefs'
import type { User } from '@/types'

interface UsersListMetrics {
  total: number
  withPlan: number
  expiringOrExpired: number
  suspended: number
  active24h: number
}

/**
 * Загрузка, поиск, фильтр, сортировка, пагинация и выбор абонентов списка.
 * Клиентская обработка: список уже загружен целиком (десятки/сотни строк).
 */
export function useUsersList() {
  const { error: notifyError } = useNotifications()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [initialListPrefs] = useState(() => loadUsersListPrefs(USERS_FILTER_IDS))
  const [filter, setFilter] = useState<string>(initialListPrefs.filter)
  const [search, setSearch] = useState('')
  // Поле ввода мгновенное, пересчёт списка — по отложенному значению.
  const deferredSearch = useDeferredValue(search)
  const [sortKey, setSortKey] = useState<UsersSortKey>(initialListPrefs.sortKey)
  const [sortDir, setSortDir] = useState<UsersSortDir>(initialListPrefs.sortDir)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState<number>(() => loadPageSize())
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [stale, setStale] = useState<StaleFilter>(null)

  const reloadUsers = useCallback(async () => {
    try {
      const list = await getUsers({ includeDeleting: true })
      setUsers(list)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить пользователей')
    }
  }, [notifyError])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const list = await getUsers({ includeDeleting: true })
        if (!cancelled) setUsers(list)
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить пользователей')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [notifyError])

  // Смена фильтра сбрасывает выбор и страницу — иначе в область попадут скрытые пользователи.
  useEffect(() => {
    setSelectedIds([])
    setPage(0)
  }, [filter, search, stale])

  // Фильтр и сортировку запоминаем между заходами; поиск — нет (временный запрос).
  useEffect(() => {
    saveUsersListPrefs({ filter, sortKey, sortDir })
  }, [filter, sortKey, sortDir])

  // Смена сортировки/размера страницы возвращает на первую страницу; размер запоминаем.
  useEffect(() => {
    setPage(0)
    savePageSize(pageSize)
  }, [sortKey, sortDir, pageSize])
  const filteredUsers = useMemo(() => {
    const q = deferredSearch.trim().toLowerCase()
    let list = users.filter((u) => {
      if (!q) return true
      const hay = [
        u.username,
        String(u.id),
        u.telegram_id ?? '',
        u.client_base_name ?? '',
        u.owned_config_base_name ?? '',
        u.note ?? '',
      ]
        .join('\u0000')
        .toLowerCase()
      return hay.includes(q)
    })
    const now = new Date()
    now.setHours(0, 0, 0, 0)
    const weekLater = new Date(now)
    weekLater.setDate(weekLater.getDate() + 7)
    // «Удаляется» — отдельный список: обычные фильтры удаляемых не показывают.
    const deleting = filter === 'deleting'
    list = list.filter((u) => (u.provision_state === 'pending_deletion') === deleting)
    list = list.filter((u) => {
      if (stale == null) return true
      if (stale === 'never') return !u.last_seen_at
      const seen = u.last_seen_at ? parseTimestamp(u.last_seen_at)?.getTime() : null
      if (seen == null) return false
      return Date.now() - seen > stale * 86_400_000
    })
    switch (filter) {
      case 'attention':
        list = list.filter(
          (u) => u.provision_state === 'partial' || u.provision_state === 'pending',
        )
        break
      case 'unmanaged':
        list = list.filter((u) => u.provision_state === 'unmanaged')
        break
      case 'expiring':
        list = list.filter((u) => {
          if (!u.access_until) return false
          const d = new Date(u.access_until)
          return d >= now && d <= weekLater
        })
        break
      case 'expired':
        list = list.filter((u) => {
          if (!u.access_until) return false
          return new Date(u.access_until) < now
        })
        break
      case 'suspended':
        list = list.filter((u) => Boolean(u.suspended_at))
        break
      case 'inactive':
        list = list.filter((u) => u.is_active === false)
        break
      default:
        break
    }
    const dir = sortDir === 'asc' ? 1 : -1
    return list.sort((a, b) => {
      if (sortKey === 'traffic') {
        return dir * ((a.traffic_consumed_bytes ?? 0) - (b.traffic_consumed_bytes ?? 0))
      }
      const field =
        sortKey === 'last_seen'
          ? 'last_seen_at'
          : (sortKey as 'username' | 'created_at' | 'access_until')
      const av = a[field] ?? ''
      const bv = b[field] ?? ''
      return dir * String(av).localeCompare(String(bv), 'ru')
    })
  }, [users, filter, deferredSearch, sortKey, sortDir, stale])

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / pageSize))
  const safePage = Math.min(page, totalPages - 1)
  const pagedUsers = filteredUsers.slice(safePage * pageSize, (safePage + 1) * pageSize)

  // Массовые действия: выбранные галочками, иначе — весь отфильтрованный список.
  const bulkTargetIds = selectedIds.length > 0 ? selectedIds : filteredUsers.map((u) => u.id)

  // «Выбрать всех на странице»: состояние чекбокса по текущей странице пагинации.
  const pagedUserIds = pagedUsers.map((u) => u.id)
  const selectedOnPage = pagedUserIds.filter((id) => selectedIds.includes(id)).length
  const allPageSelected = pagedUserIds.length > 0 && selectedOnPage === pagedUserIds.length
  const somePageSelected = selectedOnPage > 0 && !allPageSelected

  const listMetrics = useMemo<UsersListMetrics>(() => {
    const now = Date.now()
    const week = now + 7 * 86400000
    const dayAgo = now - 86400000
    let withPlan = 0
    let expiringOrExpired = 0
    let suspended = 0
    let active24h = 0
    for (const u of users) {
      if (u.client_base_name && u.provision_state && u.provision_state !== 'unmanaged') withPlan += 1
      if (u.suspended_at) suspended += 1
      const seenAt = u.last_seen_at ? parseTimestamp(u.last_seen_at)?.getTime() : null
      if (seenAt != null && seenAt >= dayAgo) active24h += 1
      if (u.access_until) {
        const t = new Date(u.access_until).getTime()
        if (t < now || t <= week) expiringOrExpired += 1
      }
    }
    return { total: users.length, withPlan, expiringOrExpired, suspended, active24h }
  }, [users])

  return {
    users,
    setUsers,
    loading,
    reloadUsers,
    filter,
    setFilter,
    search,
    setSearch,
    stale,
    setStale,
    sortKey,
    setSortKey,
    sortDir,
    setSortDir,
    page,
    setPage,
    pageSize,
    setPageSize,
    selectedIds,
    setSelectedIds,
    filteredUsers,
    totalPages,
    safePage,
    pagedUsers,
    bulkTargetIds,
    pagedUserIds,
    allPageSelected,
    somePageSelected,
    listMetrics,
  }
}

