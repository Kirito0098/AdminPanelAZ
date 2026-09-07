import { describe, expect, it } from 'vitest'

import { settingsSectionNeedsNodeSettings, settingsSectionNeedsUsers } from './settingsPageLoads'

describe('settingsSectionNeedsNodeSettings', () => {
  it('is true only for maintenance', () => {
    expect(settingsSectionNeedsNodeSettings('maintenance')).toBe(true)
    expect(settingsSectionNeedsNodeSettings('personal')).toBe(false)
    expect(settingsSectionNeedsNodeSettings('users')).toBe(false)
    expect(settingsSectionNeedsNodeSettings('vpn_network')).toBe(false)
    expect(settingsSectionNeedsNodeSettings(null)).toBe(false)
  })
})

describe('settingsSectionNeedsUsers', () => {
  it('is true only for admin on users', () => {
    expect(settingsSectionNeedsUsers('users', true)).toBe(true)
    expect(settingsSectionNeedsUsers('users', false)).toBe(false)
    expect(settingsSectionNeedsUsers('personal', true)).toBe(false)
    expect(settingsSectionNeedsUsers('maintenance', true)).toBe(false)
    expect(settingsSectionNeedsUsers(null, true)).toBe(false)
  })
})
