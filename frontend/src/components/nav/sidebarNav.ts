// frontend/src/components/nav/sidebarNav.ts
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  ClipboardList,
  Cpu,
  FileText,
  GitBranch,
  Globe,
  HardDrive,
  LayoutDashboard,
  Network,
  Send,
  Server,
  Settings,
  Settings2,
  Shield,
  Ticket,
} from 'lucide-react'

export type SidebarNavItem = {
  to: string
  label: string
  icon: LucideIcon
  end: boolean
  adminOnly: boolean
  featureKey: string | null
  featureAnyOf?: readonly string[]
}

export type SidebarNavGroup = {
  label: string
  items: SidebarNavItem[]
}

export const SIDEBAR_NAV_GROUPS: SidebarNavGroup[] = [
  {
    label: 'Клиенты',
    items: [
      { to: '/', label: 'Клиенты', icon: LayoutDashboard, end: true, adminOnly: false, featureKey: null },
      {
        to: '/subscription',
        label: 'Подписка',
        icon: Ticket,
        end: false,
        adminOnly: true,
        featureKey: null,
        featureAnyOf: ['client_portal', 'unlock_codes'] as const,
      },
    ],
  },
  {
    label: 'Сеть',
    items: [
      { to: '/routing', label: 'Маршрутизация / CIDR', icon: GitBranch, end: false, adminOnly: true, featureKey: 'routing' },
      { to: '/antizapret', label: 'Конфиг AntiZapret', icon: Settings2, end: false, adminOnly: true, featureKey: 'antizapret_config' },
      { to: '/proxy', label: 'Прокси', icon: Network, end: false, adminOnly: true, featureKey: 'proxy_nodes' },
      { to: '/warper', label: 'AZ-WARP', icon: Globe, end: false, adminOnly: true, featureKey: 'warper' },
      { to: '/awg2', label: 'AZ-AWG2', icon: Shield, end: false, adminOnly: true, featureKey: 'awg2' },
    ],
  },
  {
    label: 'Наблюдение',
    items: [
      { to: '/monitoring', label: 'NOC Мониторинг', icon: Activity, end: false, adminOnly: true, featureKey: 'logs_dashboard' },
      { to: '/traffic', label: 'Мониторинг трафика', icon: HardDrive, end: false, adminOnly: false, featureKey: 'traffic_sync' },
      {
        to: '/logs',
        label: 'Журналы',
        icon: ClipboardList,
        end: false,
        adminOnly: true,
        featureKey: null,
        featureAnyOf: ['logs_dashboard', 'action_logs'] as const,
      },
      { to: '/server-monitor', label: 'Сервер', icon: Cpu, end: false, adminOnly: true, featureKey: 'server_monitor' },
    ],
  },
  {
    label: 'Панель',
    items: [
      { to: '/nodes', label: 'Узлы', icon: Server, end: false, adminOnly: true, featureKey: 'nodes' },
      { to: '/settings', label: 'Настройки', icon: Settings, end: false, adminOnly: true, featureKey: null },
      { to: '/telegram', label: 'Telegram', icon: Send, end: false, adminOnly: true, featureKey: 'telegram' },
      { to: '/edit-files', label: 'Редактор файлов', icon: FileText, end: false, adminOnly: true, featureKey: 'edit_files' },
    ],
  },
]

export function isSidebarNavItemVisible(
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

export function getVisibleSidebarNavGroups(
  userRole: string | undefined,
  isEnabled: (key: string) => boolean,
): SidebarNavGroup[] {
  return SIDEBAR_NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => isSidebarNavItemVisible(item, userRole, isEnabled)),
  })).filter((group) => group.items.length > 0)
}
