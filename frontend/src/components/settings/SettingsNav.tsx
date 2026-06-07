import type { LucideIcon } from 'lucide-react'
import {
  Archive,
  Download,
  FlaskConical,
  KeyRound,
  Puzzle,
  Send,
  Shield,
  User,
  Users,
  Wrench,
} from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

export type SettingsSection =
  | 'personal'
  | 'maintenance'
  | 'backup'
  | 'telegram'
  | 'security'
  | 'modules'
  | 'updates'
  | 'tests'
  | 'users'

interface NavItem {
  id: SettingsSection
  label: string
  icon: LucideIcon
  description: string
  settingsTab?: 'backup' | 'telegram' | 'security' | 'tests'
}

interface NavGroup {
  label: string
  adminOnly?: boolean
  items: NavItem[]
}

export const SETTINGS_NAV_GROUPS: NavGroup[] = [
  {
    label: 'Учётная запись',
    items: [
      {
        id: 'personal',
        label: 'Личные',
        icon: User,
        description: 'Тема, пароль, путь AntiZapret',
      },
      {
        id: 'security',
        label: 'Безопасность',
        icon: Shield,
        description: '2FA, IP whitelist, защита от сканеров',
        settingsTab: 'security',
      },
    ],
  },
  {
    label: 'Операции',
    adminOnly: true,
    items: [
      {
        id: 'maintenance',
        label: 'Обслуживание',
        icon: Wrench,
        description: 'Профили клиентов и перезапуск VPN',
      },
      {
        id: 'backup',
        label: 'Бэкапы',
        icon: Archive,
        description: 'Резервные копии панели и списков',
        settingsTab: 'backup',
      },
    ],
  },
  {
    label: 'Интеграции',
    adminOnly: true,
    items: [
      {
        id: 'telegram',
        label: 'Telegram',
        icon: Send,
        description: 'Уведомления и доставка бэкапов',
        settingsTab: 'telegram',
      },
    ],
  },
  {
    label: 'Панель',
    adminOnly: true,
    items: [
      {
        id: 'modules',
        label: 'Модули',
        icon: Puzzle,
        description: 'Фоновые задачи и разделы',
      },
      {
        id: 'updates',
        label: 'Обновления',
        icon: Download,
        description: 'Git pull из origin/main',
      },
      {
        id: 'tests',
        label: 'Тесты',
        icon: FlaskConical,
        description: 'Smoke-тесты backend (pytest)',
        settingsTab: 'tests',
      },
      {
        id: 'users',
        label: 'Пользователи',
        icon: Users,
        description: 'Учётные записи и роли',
      },
    ],
  },
]

interface SettingsNavProps {
  active: SettingsSection
  onChange: (section: SettingsSection) => void
  isAdmin: boolean
  isTabEnabled: (tab: string) => boolean
}

export default function SettingsNav({ active, onChange, isAdmin, isTabEnabled }: SettingsNavProps) {
  const visibleGroups = SETTINGS_NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (group.adminOnly && !isAdmin) return false
      if (item.id === 'security' && !isAdmin) return false
      if (item.settingsTab && !isTabEnabled(item.settingsTab)) return false
      return true
    }),
  })).filter((group) => group.items.length > 0)

  return (
    <nav className="space-y-4" aria-label="Разделы настроек">
      {visibleGroups.map((group, groupIndex) => (
        <div key={group.label}>
          {groupIndex > 0 && <Separator className="mb-4 lg:hidden" />}
          <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {group.label}
          </p>
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
          <KeyRound size={14} className="mb-1.5 inline" /> Расширенные разделы доступны только администраторам
        </div>
      )}
    </nav>
  )
}

export function getDefaultSection(isAdmin: boolean): SettingsSection {
  return 'personal'
}

export function isSectionAvailable(
  section: SettingsSection,
  isAdmin: boolean,
  isTabEnabled: (tab: string) => boolean,
): boolean {
  for (const group of SETTINGS_NAV_GROUPS) {
    for (const item of group.items) {
      if (item.id !== section) continue
      if (group.adminOnly && !isAdmin) return false
      if (item.id === 'security' && !isAdmin) return false
      if (item.settingsTab && !isTabEnabled(item.settingsTab)) return false
      return true
    }
  }
  return false
}
