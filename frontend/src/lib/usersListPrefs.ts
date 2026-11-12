import { createStorage } from './safeStorage'

/** Ключи сортировки списка пользователей — совпадают с полями `User`. */
export type UsersSortKey = 'username' | 'created_at' | 'access_until' | 'traffic' | 'last_seen'
export type UsersSortDir = 'asc' | 'desc'

const USERS_SORT_KEYS: readonly UsersSortKey[] = [
  'username',
  'created_at',
  'access_until',
  'traffic',
  'last_seen',
]

interface UsersListPrefs {
  filter: string
  sortKey: UsersSortKey
  sortDir: UsersSortDir
}

const DEFAULT_USERS_LIST_PREFS: UsersListPrefs = {
  filter: 'all',
  sortKey: 'username',
  sortDir: 'asc',
}

const STORAGE_PREFIX = 'users-cards'
const storage = createStorage(STORAGE_PREFIX)

/**
 * Восстанавливает фильтр и сортировку списка. Поиск намеренно не запоминаем:
 * это временный запрос, и после возврата на страницу он прятал бы абонентов.
 */
export function loadUsersListPrefs(allowedFilters: readonly string[]): UsersListPrefs {
  const filter = storage.read('filter')
  const sortKey = storage.read('sortKey')
  const sortDir = storage.read('sortDir')
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
  storage.write('filter', prefs.filter)
  storage.write('sortKey', prefs.sortKey)
  storage.write('sortDir', prefs.sortDir)
}

export const PAGE_SIZE_OPTIONS = [20, 50, 100] as const

function loadPageSize(): number {
  const raw = storage.read('pageSize')
  const n = raw ? Number.parseInt(raw, 10) : NaN
  return (PAGE_SIZE_OPTIONS as readonly number[]).includes(n) ? n : PAGE_SIZE_OPTIONS[0]
}

export function savePageSize(size: number) {
  storage.write('pageSize', String(size))
}

export { loadPageSize }

export type UsersViewMode = 'cards' | 'table'

const VIEW_MODES: readonly UsersViewMode[] = ['cards', 'table']

export function loadUsersViewMode(): UsersViewMode {
  const raw = storage.read('view')
  return raw && (VIEW_MODES as readonly string[]).includes(raw) ? (raw as UsersViewMode) : 'cards'
}

export function saveUsersViewMode(mode: UsersViewMode) {
  storage.write('view', mode)
}

