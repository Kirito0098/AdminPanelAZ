import { describe, expect, it } from 'vitest'

import { bufferGuardSavePayload, normalizeBufferGuardSettings } from './bufferGuardDraft'
import type { OpenVpnBufferGuardSettings } from '@/types'

function settings(nodeId: number, patch: Partial<OpenVpnBufferGuardSettings> = {}): OpenVpnBufferGuardSettings {
  return {
    node_id: nodeId,
    enabled: true,
    mode: 'notify',
    threshold_count: 40,
    window_seconds: 60,
    escalate_after_seconds: 30,
    cooldown_minutes: 15,
    temp_ban_minutes: 60,
    watch_units: ['vpn-udp', 'antizapret-udp'],
    ...patch,
  } as OpenVpnBufferGuardSettings
}

describe('normalizeBufferGuardSettings', () => {
  it('ties the settings to the node they were loaded for', () => {
    const normalized = normalizeBufferGuardSettings(2, settings(9, { watch_units: [] }))
    expect(normalized.node_id).toBe(2)
    expect(normalized.watch_units).toEqual(['antizapret-udp', 'vpn-udp'])
  })
})

describe('bufferGuardSavePayload', () => {
  it('saves the draft to the node it was loaded for', () => {
    const draft = normalizeBufferGuardSettings(2, settings(2, { threshold_count: 150 }))
    const payload = bufferGuardSavePayload(draft, 2)
    expect(payload?.node_id).toBe(2)
    expect(payload?.threshold_count).toBe(150)
    expect(payload?.watch_units).toEqual(['antizapret-udp', 'vpn-udp'])
  })

  it('refuses to save a draft of one node to another', () => {
    const draftOfNode1 = normalizeBufferGuardSettings(1, settings(1))
    expect(bufferGuardSavePayload(draftOfNode1, 2)).toBeNull()
    expect(bufferGuardSavePayload(draftOfNode1, null)).toBeNull()
  })
})
