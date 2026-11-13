// frontend/src/components/nav/sidebarNav.ts
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  Cable,
  FileText,
  GitBranch,
  Globe,
  LayoutDashboard,
  MessageSquare,
  Network,
  Send,
  Server,
  Settings,
  Settings2,
  Shield,
  Users,
} from 'lucide-react'

export type SidebarNavItem = {
  to: string
  label: string
  icon: LucideIcon
  end: boolean
  adminOnly: boolean
  featureKey: string | null
  featureAnyOf?: readonly string[]
  badge?: number
}

export type SidebarNavGroup = {
  /** Стабильный ключ: по нему запоминается свёрнутость группы. */
  id: string
  label: string
  items: SidebarNavItem[]
  /** По умолчанию группы раскрыты — первый заход не должен прятать обзор. */
  defaultOpen?: boolean
}

export type SidebarNav = {
  pinned: SidebarNavItem[]
  groups: SidebarNavGroup[]
  /** «Настройки» для админа; не-админу Layout подставляет «Мой профиль». */
  footer: SidebarNavItem | null
}

const PINNED: SidebarNavItem[] = [
  { to: '/', label: 'Клиенты', icon: LayoutDashboard, end: true, adminOnly: false, featureKey: 'clients_page' },
  {
    to: '/users',
    label: 'Абоненты',
    icon: Users,
    end: false,
    adminOnly: true,
    featureKey: 'user_provisioning',
  },
  {
    to: '/messages',
    label: 'Сообщения',
    icon: MessageSquare,
    end: false,
    adminOnly: true,
    featureKey: 'user_messaging',
  },
  {
    // Та же страница «Наблюдение», что и вкладки: гард по флагам, а не adminOnly,
    // чтобы роль user с включённым traffic_sync сохранила доступ к трафику.
    to: '/monitoring',
    label: 'Наблюдение',
    icon: Activity,
    end: false,
    adminOnly: false,
    featureKey: null,
    featureAnyOf: ['logs_dashboard', 'traffic_sync', 'server_monitor', 'action_logs'] as const,
  },
]

const GROUPS: SidebarNavGroup[] = [
  {
    id: 'network',
    label: 'Сеть',
    defaultOpen: true,
    items: [
      { to: '/nodes', label: 'Узлы', icon: Server, end: false, adminOnly: true, featureKey: 'nodes' },
      { to: '/proxy', label: 'Прокси', icon: Network, end: false, adminOnly: true, featureKey: 'proxy_nodes' },
      { to: '/routing', label: 'Маршрутизация', icon: GitBranch, end: false, adminOnly: true, featureKey: 'routing' },
    ],
  },
  {
    id: 'protocols',
    label: 'Протоколы',
    defaultOpen: true,
    items: [
      { to: '/protocols/antizapret', label: 'AntiZapret', icon: Settings2, end: false, adminOnly: true, featureKey: 'antizapret_config' },
      { to: '/protocols/openvpn', label: 'OpenVPN', icon: Cable, end: false, adminOnly: true, featureKey: 'openvpn' },
      { to: '/protocols/warper', label: 'AZ-WARP', icon: Globe, end: false, adminOnly: true, featureKey: 'warper' },
      { to: '/protocols/awg2', label: 'AWG 2.0', icon: Shield, end: false, adminOnly: true, featureKey: 'awg2' },
    ],
  },
  {
    id: 'system',
    label: 'Система',
    defaultOpen: true,
    items: [
      { to: '/telegram', label: 'Telegram', icon: Send, end: false, adminOnly: true, featureKey: 'telegram' },
      { to: '/edit-files', label: 'Редактор файлов', icon: FileText, end: false, adminOnly: true, featureKey: 'edit_files' },
    ],
  },
]

const FOOTER: SidebarNavItem = {
  to: '/settings',
  label: 'Настройки',
  icon: Settings,
  end: false,
  adminOnly: true,
  featureKey: null,
}

/** Полная модель без учёта ролей и флагов — нужна для ключей групп и тестов. */
export const SIDEBAR_NAV: SidebarNav = {
  pinned: PINNED,
  groups: GROUPS,
  footer: FOOTER,
}

function isSidebarNavItemVisible(
  item: SidebarNavItem,
  userRole: string | undefined,
  isEnabled: (key: string) => boolean,
): boolean {
  if (item.featureAnyOf?.length) {
    if (!item.featureAnyOf.some((key) => isEnabled(key))) return false
  } else if (item.featureKey && !isEnabled(item.featureKey)) {
    return false
  }
  if (item.adminOnly) return userRole === 'admin'
  return true
}

export function getVisibleSidebarNav(
  userRole: string | undefined,
  isEnabled: (key: string) => boolean,
): SidebarNav {
  return {
    pinned: PINNED.filter((item) => isSidebarNavItemVisible(item, userRole, isEnabled)),
    groups: GROUPS.map((group) => ({
      ...group,
      items: group.items.filter((item) => isSidebarNavItemVisible(item, userRole, isEnabled)),
    })).filter((group) => group.items.length > 0),
    footer: isSidebarNavItemVisible(FOOTER, userRole, isEnabled) ? FOOTER : null,
  }
}

/** Активность пункта — как у NavLink с его `end`. */
export function isSidebarItemActive(item: SidebarNavItem, pathname: string): boolean {
  if (item.end) return pathname === item.to
  const base = item.to.endsWith('/') ? item.to : `${item.to}/`
  return pathname === item.to || pathname.startsWith(base)
}
