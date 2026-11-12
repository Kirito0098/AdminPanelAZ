import type { CardGridCols } from './configCardViewPrefs'
import { createStorage } from './safeStorage'

export type UsersCardFieldKey =
  | 'access'
  | 'lastSeen'
  | 'nodes'
  | 'base'
  | 'tg'
  | 'names'
  | 'task'
  | 'note'

type UsersCardFieldVisibility = Record<UsersCardFieldKey, boolean>

export interface UsersCardViewPrefs {
  gridCols: CardGridCols
  fields: UsersCardFieldVisibility
}

export const USERS_CARD_FIELD_LABELS: Record<UsersCardFieldKey, string> = {
  access: 'Срок доступа',
  lastSeen: 'Активность',
  nodes: 'Узлы',
  base: 'База имени',
  tg: 'Telegram',
  names: 'Число имён конфигов',
  task: 'Задача',
  note: 'Заметка',
}

const FIELD_KEYS = Object.keys(USERS_CARD_FIELD_LABELS) as UsersCardFieldKey[]
const GRID_COLS: readonly CardGridCols[] = ['auto', '1', '2', '3', '4']

export const DEFAULT_USERS_CARD_VIEW_PREFS: UsersCardViewPrefs = {
  gridCols: 'auto',
  fields: {
    access: true,
    lastSeen: true,
    nodes: true,
    base: true,
    tg: true,
    names: true,
    task: true,
    note: true,
  },
}

const STORAGE_PREFIX = 'users-cards'
const storage = createStorage(STORAGE_PREFIX)

export function loadUsersCardViewPrefs(): UsersCardViewPrefs {
  const gridCols = storage.read('gridCols')
  const fields = { ...DEFAULT_USERS_CARD_VIEW_PREFS.fields }
  for (const key of FIELD_KEYS) {
    const stored = storage.read(`field:${key}`)
    if (stored === 'true' || stored === 'false') fields[key] = stored === 'true'
  }
  return {
    gridCols: gridCols && (GRID_COLS as readonly string[]).includes(gridCols) ? (gridCols as CardGridCols) : 'auto',
    fields,
  }
}

export function saveUsersCardViewPrefs(prefs: UsersCardViewPrefs) {
  storage.write('gridCols', prefs.gridCols)
  for (const key of FIELD_KEYS) storage.write(`field:${key}`, String(prefs.fields[key]))
}
