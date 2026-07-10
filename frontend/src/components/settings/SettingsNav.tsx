import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  Archive,
  Download,
  FlaskConical,
  Globe,
  Puzzle,
  QrCode,
  RefreshCw,
  Shield,
  User,
  Users,
  Wrench,
} from 'lucide-react'
import { SECTION_META } from '@/components/settings/settingsLabels'

export type SettingsSection =
  | 'personal'
  | 'users'
  | 'security'
  | 'config_delivery'
  | 'maintenance'
  | 'backup'
  | 'monitoring'
  | 'vpn_network'
  | 'modules'
  | 'updates'
  | 'panel_ops'
  | 'tests'

type SettingsTabKey =
  | 'backup'
  | 'maintenance'
  | 'security'
  | 'tests'
  | 'users'
  | 'updates'
  | 'vpn_network'
  | 'qr_downloads'
  | 'monitoring'

export interface SettingsNavItem {
  id: SettingsSection
  label: string
  icon: LucideIcon
  description: string
  settingsTab?: SettingsTabKey
  adminOnly?: boolean
}

export interface SettingsNavGroup {
  label: string
  description?: string
  adminOnly?: boolean
  items: SettingsNavItem[]
}

function navItem(
  id: SettingsSection,
  icon: LucideIcon,
  extra?: Pick<SettingsNavItem, 'settingsTab' | 'adminOnly'>,
): SettingsNavItem {
  const meta = SECTION_META[id]
  return {
    id,
    label: meta.title,
    icon,
    description: meta.description,
    ...extra,
  }
}

export const SETTINGS_NAV_GROUPS: SettingsNavGroup[] = [
  {
    label: 'Личное',
    description: 'Только ваш аккаунт',
    items: [navItem('personal', User)],
  },
  {
    label: 'Кто может войти',
    description: 'Учётные записи и защита',
    adminOnly: true,
    items: [
      navItem('users', Users, { settingsTab: 'users' }),
      navItem('security', Shield, { settingsTab: 'security' }),
    ],
  },
  {
    label: 'VPN',
    description: 'Профили клиентов и службы',
    adminOnly: true,
    items: [
      navItem('config_delivery', QrCode, { settingsTab: 'qr_downloads' }),
      navItem('maintenance', Wrench, { settingsTab: 'maintenance' }),
    ],
  },
  {
    label: 'Сервер',
    description: 'Сайт, копии и уведомления',
    adminOnly: true,
    items: [
      navItem('vpn_network', Globe, { settingsTab: 'vpn_network' }),
      navItem('backup', Archive, { settingsTab: 'backup' }),
      navItem('monitoring', Activity, { settingsTab: 'monitoring' }),
    ],
  },
  {
    label: 'Панель',
    description: 'Функции и обновления',
    adminOnly: true,
    items: [
      navItem('modules', Puzzle),
      navItem('updates', Download, { settingsTab: 'updates' }),
      navItem('panel_ops', RefreshCw),
      navItem('tests', FlaskConical, { settingsTab: 'tests' }),
    ],
  },
]

export function isNavItemVisible(
  item: SettingsNavItem,
  group: SettingsNavGroup,
  isAdmin: boolean,
  isTabEnabled: (tab: string) => boolean,
  isModuleEnabled: (key: string) => boolean,
): boolean {
  if ((group.adminOnly || item.adminOnly) && !isAdmin) return false
  if (item.id === 'config_delivery') {
    return isTabEnabled('qr_downloads') || isModuleEnabled('openvpn')
  }
  if (item.settingsTab && !isTabEnabled(item.settingsTab)) return false
  return true
}

export function getVisibleNavGroups(
  isAdmin: boolean,
  isTabEnabled: (tab: string) => boolean,
  isModuleEnabled: (key: string) => boolean = () => true,
): SettingsNavGroup[] {
  return SETTINGS_NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) =>
      isNavItemVisible(item, group, isAdmin, isTabEnabled, isModuleEnabled),
    ),
  })).filter((group) => group.items.length > 0)
}

export function getVisibleNavItems(
  isAdmin: boolean,
  isTabEnabled: (tab: string) => boolean,
  isModuleEnabled: (key: string) => boolean = () => true,
): SettingsNavItem[] {
  return getVisibleNavGroups(isAdmin, isTabEnabled, isModuleEnabled).flatMap((group) => group.items)
}

export function getDefaultSection(_isAdmin: boolean): SettingsSection {
  return 'personal'
}

export function isValidSettingsSection(section: string | undefined): section is SettingsSection {
  if (!section) return false
  return SETTINGS_NAV_GROUPS.some((group) => group.items.some((item) => item.id === section))
}

export function isSectionAvailable(
  section: SettingsSection,
  isAdmin: boolean,
  isTabEnabled: (tab: string) => boolean,
  isModuleEnabled: (key: string) => boolean = () => true,
): boolean {
  for (const group of SETTINGS_NAV_GROUPS) {
    for (const item of group.items) {
      if (item.id !== section) continue
      return isNavItemVisible(item, group, isAdmin, isTabEnabled, isModuleEnabled)
    }
  }
  return false
}
