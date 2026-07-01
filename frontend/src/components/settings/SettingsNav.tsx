import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  Archive,
  Download,
  FlaskConical,
  Globe,
  KeyRound,
  Puzzle,
  QrCode,
  Shield,
  User,
  Users,
  Wrench,
} from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
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

interface NavItem {
  id: SettingsSection
  label: string
  icon: LucideIcon
  description: string
  settingsTab?: SettingsTabKey
  adminOnly?: boolean
}

interface NavGroup {
  label: string
  description?: string
  adminOnly?: boolean
  items: NavItem[]
}

function navItem(
  id: SettingsSection,
  icon: LucideIcon,
  extra?: Pick<NavItem, 'settingsTab' | 'adminOnly'>,
): NavItem {
  const meta = SECTION_META[id]
  return {
    id,
    label: meta.title,
    icon,
    description: meta.description,
    ...extra,
  }
}

export const SETTINGS_NAV_GROUPS: NavGroup[] = [
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
      navItem('tests', FlaskConical, { settingsTab: 'tests' }),
    ],
  },
]

interface SettingsNavProps {
  active: SettingsSection
  onChange: (section: SettingsSection) => void
  isAdmin: boolean
  isTabEnabled: (tab: string) => boolean
  isModuleEnabled?: (key: string) => boolean
}

function isNavItemVisible(
  item: NavItem,
  group: NavGroup,
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

export default function SettingsNav({
  active,
  onChange,
  isAdmin,
  isTabEnabled,
  isModuleEnabled = () => true,
}: SettingsNavProps) {
  const visibleGroups = SETTINGS_NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) =>
      isNavItemVisible(item, group, isAdmin, isTabEnabled, isModuleEnabled),
    ),
  })).filter((group) => group.items.length > 0)

  return (
    <nav className="space-y-5" aria-label="Разделы настроек">
      {visibleGroups.map((group, groupIndex) => (
        <div key={group.label}>
          {groupIndex > 0 && <Separator className="mb-4 lg:hidden" />}
          <div className="mb-2 px-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {group.label}
            </p>
            {group.description && (
              <p className="mt-0.5 text-xs text-muted-foreground/80">{group.description}</p>
            )}
          </div>
          <ul className="space-y-1">
            {group.items.map((item) => {
              const isActive = active === item.id
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onChange(item.id)}
                    className={cn(
                      'flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground shadow-sm'
                        : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                    )}
                  >
                    <item.icon size={18} className="mt-0.5 shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-medium leading-none">{item.label}</span>
                      <span
                        className={cn(
                          'mt-1 block text-xs leading-snug',
                          isActive ? 'text-primary-foreground/80' : 'text-muted-foreground',
                        )}
                      >
                        {item.description}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      ))}

      {!isAdmin && (
        <div className="rounded-lg border border-dashed bg-muted/30 px-3 py-3 text-xs text-muted-foreground">
          <KeyRound size={14} className="mb-1.5 inline" /> Остальные разделы настроек доступны только администратору
        </div>
      )}
    </nav>
  )
}

export function getVisibleNavItems(
  isAdmin: boolean,
  isTabEnabled: (tab: string) => boolean,
  isModuleEnabled: (key: string) => boolean = () => true,
): NavItem[] {
  return SETTINGS_NAV_GROUPS.flatMap((group) =>
    group.items.filter((item) => isNavItemVisible(item, group, isAdmin, isTabEnabled, isModuleEnabled)),
  )
}

export function getDefaultSection(_isAdmin: boolean): SettingsSection {
  return 'personal'
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
