import { describe, expect, it } from 'vitest'

import {
  applyBufferGuardNumberInputs,
  bufferGuardNumberError,
  bufferGuardSavePayload,
  commitBufferGuardNumber,
  normalizeBufferGuardSettings,
} from './bufferGuardDraft'
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

describe('bufferGuardNumberError', () => {
  it('accepts intermediate text while it is typed and flags only what cannot be saved as is', () => {
    expect(bufferGuardNumberError('threshold_count', '150')).toBeNull()
    expect(bufferGuardNumberError('threshold_count', '1')).toBe('От 10 до 1000000')
    expect(bufferGuardNumberError('window_seconds', '601')).toBe('От 10 до 600')
    expect(bufferGuardNumberError('cooldown_minutes', '')).toBe('От 1 до 1440')
    expect(bufferGuardNumberError('temp_ban_minutes', '7.5')).toBe('От 5 до 10080')
  })
})

describe('commitBufferGuardNumber', () => {
  it('keeps a value typed within the limits', () => {
    expect(commitBufferGuardNumber('threshold_count', '150', 40)).toBe(150)
    expect(commitBufferGuardNumber('window_seconds', ' 90 ', 60)).toBe(90)
  })

  it('brings a value outside the limits to the nearest limit', () => {
    expect(commitBufferGuardNumber('threshold_count', '1', 40)).toBe(10)
    expect(commitBufferGuardNumber('escalate_after_seconds', '5000', 30)).toBe(300)
    expect(commitBufferGuardNumber('cooldown_minutes', '-3', 15)).toBe(1)
    expect(commitBufferGuardNumber('temp_ban_minutes', '7.6', 60)).toBe(8)
  })

  it('keeps the previous value when the field was left empty or unreadable', () => {
    expect(commitBufferGuardNumber('threshold_count', '', 40)).toBe(40)
    expect(commitBufferGuardNumber('window_seconds', 'abc', 60)).toBe(60)
  })
})

describe('applyBufferGuardNumberInputs', () => {
  it('commits every field still being typed, so saving never sends text outside the limits', () => {
    const draft = normalizeBufferGuardSettings(2, settings(2))
    const next = applyBufferGuardNumberInputs(draft, { threshold_count: '150', window_seconds: '5', cooldown_minutes: '' })
    expect(next.threshold_count).toBe(150)
    expect(next.window_seconds).toBe(10)
    expect(next.cooldown_minutes).toBe(15)
    expect(next.temp_ban_minutes).toBe(60)
  })

  it('returns the draft itself when nothing is being typed', () => {
    const draft = normalizeBufferGuardSettings(2, settings(2))
    expect(applyBufferGuardNumberInputs(draft, {})).toBe(draft)
  })
})
