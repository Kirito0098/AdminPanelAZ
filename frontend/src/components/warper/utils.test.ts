import { describe, expect, it, vi } from 'vitest'

import type { WarperHealthResponse } from '@/types'

import { donorLinkMode, extractProxyLink, saveSwitch, warperToggleLabel } from './utils'

describe('warperToggleLabel', () => {
  const health = (patch: Partial<WarperHealthResponse>): WarperHealthResponse => ({
    installed: true,
    active: false,
    conflict_antizapret_warp: false,
    ...patch,
  })

  it('offers to switch off an active AZ-WARP', () => {
    expect(warperToggleLabel(health({ active: true }))).toBe('Выключить')
  })

  it('offers to finish switching off when the DNS patch outlived sing-box', () => {
    expect(warperToggleLabel(health({ dns_patch_orphaned: true }))).toBe('Выключить полностью')
  })

  it('offers to switch on otherwise', () => {
    expect(warperToggleLabel(health({}))).toBe('Включить')
    expect(warperToggleLabel(null)).toBe('Включить')
  })
})

describe('saveSwitch', () => {
  it('shows the new position while saving and keeps it after a successful save', async () => {
    const shown: boolean[] = []
    const save = vi.fn(async () => {
      expect(shown).toEqual([true])
      return true
    })

    expect(await saveSwitch(false, true, (value) => shown.push(value), save)).toBe(true)
    expect(save).toHaveBeenCalledTimes(1)
    expect(shown).toEqual([true])
  })

  it('puts the previous position back when saving failed', async () => {
    const shown: boolean[] = []

    expect(await saveSwitch(false, true, (value) => shown.push(value), async () => false)).toBe(false)
    expect(shown).toEqual([true, false])
  })

  it('puts the previous position back when saving throws', async () => {
    const shown: Array<boolean | null> = []
    const failing = async (): Promise<boolean> => {
      throw new Error('offline')
    }

    await expect(saveSwitch<boolean | null>(true, false, (value) => shown.push(value), failing)).rejects.toThrow(
      'offline',
    )
    expect(shown).toEqual([false, true])
  })
})

describe('extractProxyLink', () => {
  const ss = 'ss://MjAyMi1ibGFrZTM@203.0.113.5:8444#warperslave'
  const vless = 'vless://uuid@203.0.113.5:443?security=reality&sni=example.com#warperslave'

  it('keeps a bare link', () => {
    expect(extractProxyLink(`  ${ss}\n`)).toBe(ss)
  })

  it('takes the link from warperslave link output and warper mode command', () => {
    expect(extractProxyLink(`Shadowsocks: ${ss}`)).toBe(ss)
    expect(extractProxyLink(`VLESS+Reality: ${vless}`)).toBe(vless)
    expect(extractProxyLink(`warper mode vless '${vless}'`)).toBe(vless)
  })

  it('returns text without a link as is, so validation can reject it', () => {
    expect(extractProxyLink(' 203.0.113.5 ')).toBe('203.0.113.5')
  })
})

describe('donorLinkMode', () => {
  it('maps donor link schemes to outbound modes', () => {
    expect(donorLinkMode('ss://x@h:1')).toBe('slave')
    expect(donorLinkMode('vless://x@h:1')).toBe('vless')
    expect(donorLinkMode('hy2://x@h:1')).toBe('hy2')
    expect(donorLinkMode('hysteria2://x@h:1')).toBe('hy2')
    expect(donorLinkMode('trojan://x@h:1')).toBeNull()
  })
})
