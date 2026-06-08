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
  | 'users'
  | 'security'
  | 'config_delivery'
  | 'maintenance'
  | 'backup'
  | 'monitoring'
  | 'vpn_network'
  | 'telegram'
  | 'modules'
  | 'updates'
  | 'tests'

type SettingsTabKey =
  | 'backup'
  | 'maintenance'
  | 'telegram'
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
  adminOnly?: boolean
  items: NavItem[]
}

export const SETTINGS_NAV_GROUPS: NavGroup[] = [
  {
    label: 'Учётная запись',
    items: [
      {
        id: 'personal',
        label: 'Профиль',
        icon: User,
        description: 'Тема, пароль и двухфакторная аутентификация',
      },
      {
        id: 'users',
        label: 'Пользователи',
        icon: Users,
        description: 'Учётные записи, роли и доступ viewer',
        settingsTab: 'users',
        adminOnly: true,
      },
    ],
  },
  {
    label: 'Безопасность',
    adminOnly: true,
    items: [
      {
        id: 'security',
        label: 'Доступ к панели',
        icon: Shield,
        description: 'IP whitelist, сканеры и активные баны',
        settingsTab: 'security',
      },
      {
        id: 'config_delivery',
        label: 'Раздача конфигов',
        icon: QrCode,
        description: 'Одноразовые QR-ссылки и публичные route-файлы',
        settingsTab: 'qr_downloads',
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
        description: 'Профили клиентов, путь AntiZapret и перезапуск VPN',
        settingsTab: 'maintenance',
      },
      {
        id: 'backup',
        label: 'Резервные копии',
        icon: Archive,
        description: 'Создание, восстановление и автоматизация бэкапов',
        settingsTab: 'backup',
      },
      {
        id: 'monitoring',
        label: 'Мониторинг',
        icon: Activity,
        description: 'Пороги CPU/RAM и интервалы Telegram-оповещений',
        settingsTab: 'monitoring',
      },
      {
        id: 'vpn_network',
        label: 'Сеть и публикация',
        icon: Globe,
        description: 'HTTPS, домен и reverse-proxy',
        settingsTab: 'vpn_network',
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
    label: 'Система',
    adminOnly: true,
    items: [
      {
        id: 'modules',
        label: 'Модули',
        icon: Puzzle,
        description: 'Фоновые задачи и разделы панели',
      },
      {
        id: 'updates',
        label: 'Обновления',
        icon: Download,
        description: 'Git pull из origin/main',
        settingsTab: 'updates',
      },
      {
        id: 'tests',
        label: 'Диагностика',
        icon: FlaskConical,
        description: 'Smoke-тесты backend (pytest)',
        settingsTab: 'tests',
      },
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
