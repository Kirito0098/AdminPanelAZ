import type { CardGridCols } from './configCardViewPrefs'

export type UsersCardFieldKey = 'access' | 'nodes' | 'base' | 'tg' | 'protocols' | 'names' | 'task'

export type UsersCardFieldVisibility = Record<UsersCardFieldKey, boolean>

export interface UsersCardViewPrefs {
  gridCols: CardGridCols
  fields: UsersCardFieldVisibility
}

export const USERS_CARD_FIELD_LABELS: Record<UsersCardFieldKey, string> = {
  access: 'Срок доступа',
  nodes: 'Узлы',
  base: 'База имени',
  tg: 'Telegram',
  protocols: 'Протоколы',
  names: 'Число имён',
  task: 'Задача',
}

const FIELD_KEYS = Object.keys(USERS_CARD_FIELD_LABELS) as UsersCardFieldKey[]
const GRID_COLS: readonly CardGridCols[] = ['auto', '1', '2', '3', '4']

export const DEFAULT_USERS_CARD_VIEW_PREFS: UsersCardViewPrefs = {
  gridCols: 'auto',
  fields: {
    access: true,
    nodes: true,
    base: true,
    tg: true,
    protocols: true,
    names: true,
    task: true,
  },
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

export function loadUsersCardViewPrefs(): UsersCardViewPrefs {
  const gridCols = readStored('gridCols')
  const fields = { ...DEFAULT_USERS_CARD_VIEW_PREFS.fields }
  for (const key of FIELD_KEYS) {
    const stored = readStored(`field:${key}`)
    if (stored === 'true' || stored === 'false') fields[key] = stored === 'true'
  }
  return {
    gridCols: gridCols && (GRID_COLS as readonly string[]).includes(gridCols) ? (gridCols as CardGridCols) : 'auto',
    fields,
  }
}

export function saveUsersCardViewPrefs(prefs: UsersCardViewPrefs) {
  writeStored('gridCols', prefs.gridCols)
  for (const key of FIELD_KEYS) writeStored(`field:${key}`, String(prefs.fields[key]))
}
