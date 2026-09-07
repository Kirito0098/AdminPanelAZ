import type { SettingsSection } from '@/components/settings/SettingsNav'

/** Parent SettingsPage should call GET /settings only for sections that use that payload. */
export function settingsSectionNeedsNodeSettings(section: SettingsSection | null): boolean {
  return section === 'maintenance'
}

/** Parent SettingsPage should call GET /users only for the users section. */
export function settingsSectionNeedsUsers(section: SettingsSection | null, isAdmin: boolean): boolean {
  return Boolean(isAdmin && section === 'users')
}
