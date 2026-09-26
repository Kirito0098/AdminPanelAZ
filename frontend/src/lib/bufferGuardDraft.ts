import type { OpenVpnBufferGuardSettings } from '@/types'

export const DEFAULT_WATCH_UNITS: string[] = ['antizapret-udp', 'vpn-udp']

export function sortUnits(units: string[]): string[] {
  return [...units].sort()
}

function watchUnitsOrDefault(units: string[] | null | undefined): string[] {
  return units && units.length > 0 ? sortUnits(units) : [...DEFAULT_WATCH_UNITS]
}

/** Settings as the card keeps them: tied to the node they were loaded for. */
export function normalizeBufferGuardSettings(
  nodeId: number,
  settings: OpenVpnBufferGuardSettings,
): OpenVpnBufferGuardSettings {
  return { ...settings, node_id: nodeId, watch_units: watchUnitsOrDefault(settings.watch_units) }
}

/** Must match the limits the backend enforces for these fields. */
export const BUFFER_GUARD_NUMBER_LIMITS = {
  threshold_count: { min: 10, max: 1_000_000 },
  window_seconds: { min: 10, max: 600 },
  escalate_after_seconds: { min: 5, max: 300 },
  cooldown_minutes: { min: 1, max: 1440 },
  temp_ban_minutes: { min: 5, max: 10_080 },
} as const

export type BufferGuardNumberField = keyof typeof BUFFER_GUARD_NUMBER_LIMITS

/** Text of the number fields as typed, kept until the field loses focus. */
export type BufferGuardNumberInputs = Partial<Record<BufferGuardNumberField, string>>

function parseWhole(text: string): number | null {
  const trimmed = text.trim()
  if (trimmed === '') return null
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : null
}

export function bufferGuardNumberError(field: BufferGuardNumberField, text: string): string | null {
  const { min, max } = BUFFER_GUARD_NUMBER_LIMITS[field]
  const value = parseWhole(text)
  if (value !== null && Number.isInteger(value) && value >= min && value <= max) return null
  return `От ${min} до ${max}`
}

/** Empty or unreadable text keeps the previous value; anything else is rounded and brought within the limits. */
export function commitBufferGuardNumber(field: BufferGuardNumberField, text: string, previous: number): number {
  const value = parseWhole(text)
  if (value === null) return previous
  const { min, max } = BUFFER_GUARD_NUMBER_LIMITS[field]
  return Math.min(max, Math.max(min, Math.round(value)))
}

export function applyBufferGuardNumberInputs(
  draft: OpenVpnBufferGuardSettings,
  inputs: BufferGuardNumberInputs,
): OpenVpnBufferGuardSettings {
  let next = draft
  for (const field of Object.keys(inputs) as BufferGuardNumberField[]) {
    const text = inputs[field]
    if (text === undefined) continue
    next = { ...next, [field]: commitBufferGuardNumber(field, text, draft[field]) }
  }
  return next
}

/** The draft is saved only to the node it was loaded for, and only while the card shows that node. */
export function bufferGuardSavePayload(
  draft: OpenVpnBufferGuardSettings,
  shownNodeId: number | null,
): OpenVpnBufferGuardSettings | null {
  if (shownNodeId === null || draft.node_id !== shownNodeId) return null
  return { ...draft, watch_units: watchUnitsOrDefault(draft.watch_units) }
}
