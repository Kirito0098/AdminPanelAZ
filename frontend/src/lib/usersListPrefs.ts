/** Ключи сортировки списка пользователей — совпадают с полями `User`. */
export type UsersSortKey = 'username' | 'created_at' | 'access_until' | 'traffic' | 'last_seen'
export type UsersSortDir = 'asc' | 'desc'

export const USERS_SORT_KEYS: readonly UsersSortKey[] = [
  'username',
  'created_at',
  'access_until',
  'traffic',
  'last_seen',
]

export interface UsersListPrefs {
  filter: string
  sortKey: UsersSortKey
  sortDir: UsersSortDir
}

export const DEFAULT_USERS_LIST_PREFS: UsersListPrefs = {
  filter: 'all',
  sortKey: 'username',
  sortDir: 'asc',
}

const STORAGE_PREFIX = 'users-cards'

function readStored(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(`${STORAGE_PREFIX}:${key}`)
  } catch {
    return null
  }
}

function writeStored(key: string, value: string) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}:${key}`, value)
  } catch {
    /* ignore quota / private mode */
  }
}

/**
 * Восстанавливает фильтр и сортировку списка. Поиск намеренно не запоминаем:
 * это временный запрос, и после возврата на страницу он прятал бы абонентов.
 */
export function loadUsersListPrefs(allowedFilters: readonly string[]): UsersListPrefs {
  const filter = readStored('filter')
  const sortKey = readStored('sortKey')
  const sortDir = readStored('sortDir')
  return {
    filter: filter && allowedFilters.includes(filter) ? filter : DEFAULT_USERS_LIST_PREFS.filter,
    sortKey:
      sortKey && (USERS_SORT_KEYS as readonly string[]).includes(sortKey)
        ? (sortKey as UsersSortKey)
        : DEFAULT_USERS_LIST_PREFS.sortKey,
    sortDir: sortDir === 'asc' || sortDir === 'desc' ? sortDir : DEFAULT_USERS_LIST_PREFS.sortDir,
  }
}

export function saveUsersListPrefs(prefs: UsersListPrefs) {
  writeStored('filter', prefs.filter)
  writeStored('sortKey', prefs.sortKey)
  writeStored('sortDir', prefs.sortDir)
}

export const PAGE_SIZE_OPTIONS = [20, 50, 100] as const

function loadPageSize(): number {
  const raw = readStored('pageSize')
  const n = raw ? Number.parseInt(raw, 10) : NaN
  return (PAGE_SIZE_OPTIONS as readonly number[]).includes(n) ? n : PAGE_SIZE_OPTIONS[0]
}

export function savePageSize(size: number) {
  writeStored('pageSize', String(size))
}

export { loadPageSize }
