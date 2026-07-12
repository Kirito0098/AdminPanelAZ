import {
  Cloud,
  Database,
  FileKey,
  LayoutDashboard,
  Server,
  Settings,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'

export interface MiniTabItem {
  to: string
  label: string
  shortLabel?: string
  icon: LucideIcon
  end?: boolean
}

const USER_TABS: MiniTabItem[] = [
  { to: '/', label: 'Конфиги', icon: FileKey, end: true },
  { to: '/settings', label: 'Настройки', icon: Settings },
]

const ADMIN_TABS: MiniTabItem[] = [
  { to: '/', label: 'Дашборд', shortLabel: 'Сводка', icon: LayoutDashboard, end: true },
  { to: '/configs', label: 'Конфиги', icon: FileKey },
  { to: '/nodes', label: 'Узлы', icon: Server },
  { to: '/warper', label: 'WARP', icon: Cloud },
  { to: '/cidr', label: 'CIDR', icon: Database },
  { to: '/settings', label: 'Настройки', shortLabel: 'Настр.', icon: Settings },
]

function hapticSelect() {
  window.Telegram?.WebApp.HapticFeedback?.selectionChanged()
}

interface MiniBottomNavProps {
  isAdmin: boolean
}

export function miniTabsForRole(isAdmin: boolean): MiniTabItem[] {
  return isAdmin ? ADMIN_TABS : USER_TABS
}

export default function MiniBottomNav({ isAdmin }: MiniBottomNavProps) {
  const tabs = miniTabsForRole(isAdmin)
  const compact = tabs.length > 3

  return (
    <nav className={cn('tg-mini-tabs', compact && 'is-compact')} aria-label="Навигация мини-приложения">
      {tabs.map((tab) => {
        const Icon = tab.icon
        const caption = compact && tab.shortLabel ? tab.shortLabel : tab.label
        return (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            title={tab.label}
            aria-label={tab.label}
            onClick={hapticSelect}
            className={({ isActive }) => cn('tg-mini-tab', isActive && 'is-active')}
          >
            <Icon size={compact ? 20 : 22} className="tg-mini-tab-icon" aria-hidden />
            <span className="tg-mini-tab-label">{caption}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}
