import { describe, expect, it, vi } from 'vitest'

import { donorLinkMode, extractProxyLink, saveSwitch } from './utils'

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
