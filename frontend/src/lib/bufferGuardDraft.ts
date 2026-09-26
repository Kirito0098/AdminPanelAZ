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

/** The draft is saved only to the node it was loaded for, and only while the card shows that node. */
export function bufferGuardSavePayload(
  draft: OpenVpnBufferGuardSettings,
  shownNodeId: number | null,
): OpenVpnBufferGuardSettings | null {
  if (shownNodeId === null || draft.node_id !== shownNodeId) return null
  return { ...draft, watch_units: watchUnitsOrDefault(draft.watch_units) }
}
