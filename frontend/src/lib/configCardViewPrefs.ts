import type { CSSProperties } from 'react'

export type CardGridCols = 'auto' | '1' | '2' | '3' | '4'
export type CardButtonAccent = 'default' | 'cyan' | 'amber' | 'emerald' | 'red' | 'custom'

export const DEFAULT_CUSTOM_BUTTON_COLOR = '#00bcd4'

export interface ConfigCardFieldVisibility {
  description: boolean
  tags: boolean
  profileBadges: boolean
  metaCreated: boolean
  metaCert: boolean
  metaOwner: boolean
  metaTraffic: boolean
  metaBlock: boolean
  metaConnection: boolean
  downloadButtons: boolean
  qrButtons: boolean
  trafficLink: boolean
  dangerActions: boolean
}

export interface ConfigCardViewPrefs {
  gridCols: CardGridCols
  buttonAccent: CardButtonAccent
  customButtonColor: string
  fields: ConfigCardFieldVisibility
}

export const DEFAULT_CONFIG_CARD_VIEW_PREFS: ConfigCardViewPrefs = {
  gridCols: 'auto',
  buttonAccent: 'default',
  customButtonColor: DEFAULT_CUSTOM_BUTTON_COLOR,
  fields: {
    description: true,
    tags: true,
    profileBadges: true,
    metaCreated: true,
    metaCert: true,
    metaOwner: true,
    metaTraffic: true,
    metaBlock: true,
    metaConnection: true,
    downloadButtons: true,
    qrButtons: true,
    trafficLink: true,
    dangerActions: true,
  },
}

const STORAGE_PREFIX = 'dashboard-config-cards'
const GRID_COLS_ALLOWED: readonly CardGridCols[] = ['auto', '1', '2', '3', '4']
const ACCENT_ALLOWED: readonly CardButtonAccent[] = ['default', 'cyan', 'amber', 'emerald', 'red', 'custom']

const FIELD_KEYS = Object.keys(
  DEFAULT_CONFIG_CARD_VIEW_PREFS.fields,
) as (keyof ConfigCardFieldVisibility)[]

function readStoredString(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(`${STORAGE_PREFIX}:${key}`)
  } catch {
    return null
  }
}

function readStored<T extends string>(key: string, allowed: readonly T[]): T | null {
  if (typeof window === 'undefined') return null
  try {
    const value = window.localStorage.getItem(`${STORAGE_PREFIX}:${key}`)
    return value && (allowed as readonly string[]).includes(value) ? (value as T) : null
  } catch {
    return null
  }
}

function writeStored(key: string, value: string) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}:${key}`, value)
  } catch {
    /* ignore quota / privacy mode */
  }
}

function readFields(): ConfigCardFieldVisibility {
  const fields = { ...DEFAULT_CONFIG_CARD_VIEW_PREFS.fields }
  for (const key of FIELD_KEYS) {
    const stored = readStored(`field:${key}`, ['true', 'false'] as const)
    if (stored !== null) {
      fields[key] = stored === 'true'
    }
  }
  return fields
}

function writeFields(fields: ConfigCardFieldVisibility) {
  for (const key of FIELD_KEYS) {
    writeStored(`field:${key}`, String(fields[key]))
  }
}

export function normalizeHexColor(value: string): string | null {
  const trimmed = value.trim()
  const short = /^#([0-9a-fA-F]{3})$/.exec(trimmed)
  if (short) {
    const [r, g, b] = short[1].split('')
    return `#${r}${r}${g}${g}${b}${b}`.toLowerCase()
  }
  const full = /^#([0-9a-fA-F]{6})$/.exec(trimmed)
  if (full) return `#${full[1]}`.toLowerCase()
  return null
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const normalized = normalizeHexColor(hex)
  if (!normalized) return null
  const value = normalized.slice(1)
  return {
    r: Number.parseInt(value.slice(0, 2), 16),
    g: Number.parseInt(value.slice(2, 4), 16),
    b: Number.parseInt(value.slice(4, 6), 16),
  }
}

export function isValidHexColor(value: string): boolean {
  return normalizeHexColor(value) !== null
}

export function loadConfigCardViewPrefs(): ConfigCardViewPrefs {
  const storedCustomColor = readStoredString('customButtonColor')
  const customButtonColor = storedCustomColor && isValidHexColor(storedCustomColor)
    ? normalizeHexColor(storedCustomColor)!
    : DEFAULT_CONFIG_CARD_VIEW_PREFS.customButtonColor

  return {
    gridCols: readStored('gridCols', GRID_COLS_ALLOWED) ?? DEFAULT_CONFIG_CARD_VIEW_PREFS.gridCols,
    buttonAccent: readStored('buttonAccent', ACCENT_ALLOWED) ?? DEFAULT_CONFIG_CARD_VIEW_PREFS.buttonAccent,
    customButtonColor,
    fields: readFields(),
  }
}

export function saveConfigCardViewPrefs(prefs: ConfigCardViewPrefs) {
  writeStored('gridCols', prefs.gridCols)
  writeStored('buttonAccent', prefs.buttonAccent)
  writeStored('customButtonColor', normalizeHexColor(prefs.customButtonColor) ?? DEFAULT_CUSTOM_BUTTON_COLOR)
  writeFields(prefs.fields)
}

export function gridColsClass(cols: CardGridCols): string {
  switch (cols) {
    case '1':
      return 'grid-cols-1'
    case '2':
      return 'grid-cols-1 sm:grid-cols-2'
    case '3':
      return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
    case '4':
      return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2k:grid-cols-4'
    default:
      return 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2k:grid-cols-4'
  }
}

const accentButtonClasses: Record<Exclude<CardButtonAccent, 'default'>, string> = {
  cyan: 'border-primary/40 text-primary hover:bg-primary/10',
  amber: 'border-amber-500/40 text-amber-600 hover:bg-amber-500/10 dark:text-amber-400',
  emerald: 'border-emerald-500/40 text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-400',
  red: 'border-destructive/40 text-destructive hover:bg-destructive/10',
}

const accentBadgeClasses: Record<Exclude<CardButtonAccent, 'default'>, string> = {
  cyan: 'border-primary/25 bg-primary/10 text-primary',
  amber: 'border-amber-500/35 bg-amber-500/10 text-amber-600 dark:text-amber-400',
  emerald: 'border-emerald-500/35 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  red: 'border-destructive/35 bg-destructive/10 text-destructive',
}

export const CUSTOM_ACCENT_HOVER_CLASS = 'hover:[background-color:var(--card-accent-bg)]'

export interface AccentPresentation {
  className?: string
  style?: CSSProperties
  hoverClass?: string
}

function customAccentStyle(hex: string): CSSProperties {
  const rgb = hexToRgb(hex)
  if (!rgb) return {}
  const { r, g, b } = rgb
  return {
    '--card-accent': hex,
    '--card-accent-border': `rgba(${r}, ${g}, ${b}, 0.4)`,
    '--card-accent-bg': `rgba(${r}, ${g}, ${b}, 0.1)`,
    '--card-accent-badge-border': `rgba(${r}, ${g}, ${b}, 0.35)`,
    borderColor: 'var(--card-accent-border)',
    color: 'var(--card-accent)',
    backgroundColor: 'transparent',
  } as CSSProperties
}

function customBadgeStyle(hex: string): CSSProperties {
  const rgb = hexToRgb(hex)
  if (!rgb) return {}
  const { r, g, b } = rgb
  return {
    '--card-accent': hex,
    '--card-accent-badge-border': `rgba(${r}, ${g}, ${b}, 0.35)`,
    '--card-accent-bg': `rgba(${r}, ${g}, ${b}, 0.1)`,
    borderColor: 'var(--card-accent-badge-border)',
    color: 'var(--card-accent)',
    backgroundColor: 'var(--card-accent-bg)',
  } as CSSProperties
}

export function resolveButtonAccent(prefs: ConfigCardViewPrefs): AccentPresentation | null {
  if (prefs.buttonAccent === 'default') return null
  if (prefs.buttonAccent === 'custom') {
    const color = normalizeHexColor(prefs.customButtonColor) ?? DEFAULT_CUSTOM_BUTTON_COLOR
    return {
      style: customAccentStyle(color),
      hoverClass: CUSTOM_ACCENT_HOVER_CLASS,
    }
  }
  return { className: accentButtonClasses[prefs.buttonAccent] }
}

export function resolveBadgeAccent(prefs: ConfigCardViewPrefs): AccentPresentation | null {
  if (prefs.buttonAccent === 'default') return null
  if (prefs.buttonAccent === 'custom') {
    const color = normalizeHexColor(prefs.customButtonColor) ?? DEFAULT_CUSTOM_BUTTON_COLOR
    return { style: customBadgeStyle(color) }
  }
  return { className: accentBadgeClasses[prefs.buttonAccent] }
}

export function buttonAccentClasses(accent: CardButtonAccent): string | undefined {
  if (accent === 'default' || accent === 'custom') return undefined
  return accentButtonClasses[accent]
}

export function badgeAccentClasses(accent: CardButtonAccent): string | undefined {
  if (accent === 'default' || accent === 'custom') return undefined
  return accentBadgeClasses[accent]
}

export const FIELD_LABELS: Record<keyof ConfigCardFieldVisibility, string> = {
  description: 'Описание',
  tags: 'Теги и HA',
  profileBadges: 'Бейджи VPN / AntiZapret',
  metaCreated: 'Дата создания',
  metaCert: 'Срок сертификата',
  metaOwner: 'Владелец',
  metaTraffic: 'Трафик',
  metaBlock: 'Блокировка',
  metaConnection: 'Онлайн / офлайн',
  downloadButtons: 'Кнопки скачивания',
  qrButtons: 'QR-кнопки',
  trafficLink: 'Ссылка «Трафик»',
  dangerActions: 'Блок / удалить',
}

export const ACCENT_OPTIONS: { value: CardButtonAccent; label: string; swatchClass: string }[] = [
  { value: 'default', label: 'По умолчанию', swatchClass: 'bg-muted border-border' },
  { value: 'cyan', label: 'Cyan', swatchClass: 'bg-primary' },
  { value: 'amber', label: 'Amber', swatchClass: 'bg-amber-500' },
  { value: 'emerald', label: 'Emerald', swatchClass: 'bg-emerald-500' },
  { value: 'red', label: 'Red', swatchClass: 'bg-destructive' },
]

export const GRID_COLS_OPTIONS: { value: CardGridCols; label: string }[] = [
  { value: 'auto', label: 'Авто' },
  { value: '1', label: '1' },
  { value: '2', label: '2' },
  { value: '3', label: '3' },
  { value: '4', label: '4' },
]

export function mergeViewPrefs(partial: Partial<ConfigCardViewPrefs>): ConfigCardViewPrefs {
  return {
    ...DEFAULT_CONFIG_CARD_VIEW_PREFS,
    ...partial,
    fields: {
      ...DEFAULT_CONFIG_CARD_VIEW_PREFS.fields,
      ...partial.fields,
    },
    customButtonColor:
      partial.customButtonColor && isValidHexColor(partial.customButtonColor)
        ? normalizeHexColor(partial.customButtonColor)!
        : partial.customButtonColor ?? DEFAULT_CONFIG_CARD_VIEW_PREFS.customButtonColor,
  }
}

export function isMetaKeyVisible(
  key: string,
  fields: ConfigCardFieldVisibility,
): boolean {
  if (key === 'created') return fields.metaCreated
  if (key === 'cert') return fields.metaCert
  if (key === 'owner') return fields.metaOwner
  if (key === 'traffic') return fields.metaTraffic
  if (key === 'block') return fields.metaBlock
  if (key === 'connection') return fields.metaConnection
  return true
}
