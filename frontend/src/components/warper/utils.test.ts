import { describe, expect, it, vi } from 'vitest'

import { saveSwitch } from './utils'

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
