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
  RefreshCw,
  Shield,
  User,
  Users,
  Wrench,
} from 'lucide-react'
import { SECTION_META } from '@/components/settings/settingsLabels'
import { cn } from '@/lib/utils'

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
      navItem('panel_ops', RefreshCw),
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

function NavGroupHeader({ label, description }: { label: string; description?: string }) {
  return (
    <div className="px-3 pb-1.5 pt-4 first:pt-1">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      {description && <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{description}</p>}
    </div>
  )
}

function NavButton({
  item,
  isActive,
  onChange,
}: {
  item: NavItem
  isActive: boolean
  onChange: (section: SettingsSection) => void
}) {
  const Icon = item.icon

  return (
    <button
      type="button"
      onClick={() => onChange(item.id)}
      aria-current={isActive ? 'page' : undefined}
      className={cn(
        'group relative flex w-full items-start gap-3 rounded-xl px-2.5 py-2.5 text-left transition-colors',
        isActive
          ? 'bg-primary/10 ring-1 ring-primary/20'
          : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
      )}
    >
      <span
        className={cn(
          'absolute left-0 top-2.5 bottom-2.5 w-0.5 rounded-full transition-opacity',
          isActive ? 'bg-primary opacity-100' : 'opacity-0',
        )}
        aria-hidden
      />
      <span
        className={cn(
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border transition-colors',
          isActive
            ? 'border-primary/25 bg-primary/15 text-primary'
            : 'border-transparent bg-muted/60 text-muted-foreground group-hover:border-border/80 group-hover:bg-muted group-hover:text-foreground',
        )}
      >
        <Icon size={18} strokeWidth={2} />
      </span>
      <span className="min-w-0 flex-1 pt-0.5">
        <span
          className={cn(
            'block text-sm font-medium leading-snug',
            isActive ? 'text-foreground' : 'text-foreground',
          )}
        >
          {item.label}
        </span>
        <span
          className={cn(
            'mt-0.5 block text-xs leading-relaxed text-muted-foreground',
            !isActive && 'line-clamp-2',
          )}
        >
          {item.description}
        </span>
      </span>
    </button>
  )
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
    <nav className="space-y-1" aria-label="Разделы настроек">
      {visibleGroups.map((group) => (
        <div key={group.label}>
          <NavGroupHeader label={group.label} description={group.description} />
          <ul className="space-y-1 px-1">
            {group.items.map((item) => (
              <li key={item.id}>
                <NavButton item={item} isActive={active === item.id} onChange={onChange} />
              </li>
            ))}
          </ul>
        </div>
      ))}

      {!isAdmin && (
        <div className="mx-1 mt-4 rounded-xl border border-dashed border-border/80 bg-muted/20 px-3 py-3 text-xs leading-relaxed text-muted-foreground">
          <div className="mb-1.5 flex items-center gap-2 font-medium text-foreground">
            <KeyRound size={14} className="shrink-0 text-primary" />
            Только для администратора
          </div>
          Остальные разделы настроек скрыты — у вашей роли нет доступа к управлению панелью.
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
