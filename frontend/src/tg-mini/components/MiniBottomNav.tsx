import { useEffect, useState } from 'react'
import {
  FileKey,
  KeyRound,
  MessageSquare,
  Settings,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { getRequestsCount } from '@/api/users'

interface MiniTabItem {
  to: string
  label: string
  shortLabel?: string
  icon: LucideIcon
  end?: boolean
  featureKey?: string
  badge?: number
}

const USER_TABS: MiniTabItem[] = [
  { to: '/', label: 'Конфиги', icon: FileKey, end: true },
  { to: '/settings', label: 'Настройки', icon: Settings },
]

function adminTabs(pendingRequests: number): MiniTabItem[] {
  return [
    { to: '/', label: 'Конфиги', icon: FileKey, end: true },
    { to: '/clients', label: 'Клиенты', icon: Users },
    {
      to: '/requests',
      label: 'Заявки',
      shortLabel: 'Заявки',
      icon: MessageSquare,
      badge: pendingRequests,
    },
    { to: '/unlock-codes', label: 'Коды', shortLabel: 'Коды', icon: KeyRound, featureKey: 'unlock_codes' },
    { to: '/settings', label: 'Настройки', shortLabel: 'Настр.', icon: Settings },
  ]
}

function hapticSelect() {
  window.Telegram?.WebApp.HapticFeedback?.selectionChanged?.()
}

interface MiniBottomNavProps {
  isAdmin: boolean
  features?: Record<string, boolean>
}

function miniTabsForRole(
  isAdmin: boolean,
  pendingRequests: number,
  features?: Record<string, boolean>,
): MiniTabItem[] {
  const tabs = isAdmin ? adminTabs(pendingRequests) : USER_TABS
  return tabs.filter((tab) => {
    if (!tab.featureKey) return true
    return Boolean(features?.[tab.featureKey])
  })
}

export default function MiniBottomNav({ isAdmin, features }: MiniBottomNavProps) {
  const [pendingRequests, setPendingRequests] = useState(0)

  useEffect(() => {
    if (!isAdmin) return
    let alive = true
    const load = () => {
      void getRequestsCount('pending')
        .then((count) => {
          if (alive) setPendingRequests(count)
        })
        .catch(() => {})
    }
    load()
    const timer = window.setInterval(load, 60_000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [isAdmin])

  const tabs = miniTabsForRole(isAdmin, pendingRequests, features)
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
            <span className="tg-mini-tab-icon-wrap">
              <Icon size={compact ? 20 : 22} className="tg-mini-tab-icon" aria-hidden />
              {tab.badge != null && tab.badge > 0 && (
                <span className="tg-mini-tab-badge" aria-label={`${tab.badge} ожидает`}>
                  {tab.badge > 99 ? '99+' : tab.badge}
                </span>
              )}
            </span>
            <span className="tg-mini-tab-label">{caption}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}
