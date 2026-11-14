import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { LogOut, Menu, Moon, Radio, Shield, Sun, User } from 'lucide-react'
import NodeSelector from '@/components/NodeSelector'
import NotificationBell from '@/components/notifications/NotificationBell'
import ActiveNodeChangedBanner from '@/components/ActiveNodeChangedBanner'
import HaScopeEnforcer from '@/components/HaScopeEnforcer'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { DOCS, FEEDBACK_URL } from '@/lib/docsUrls'
import { getMessageUnreadCount } from '@/api/messages'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotificationCenter } from '@/context/NotificationCenterContext'
import { useTheme } from '@/context/ThemeContext'
import {
  getVisibleSidebarNav,
  isSidebarItemActive,
  SIDEBAR_NAV,
  type SidebarNavItem,
} from '@/components/nav/sidebarNav'
import { SidebarNavGroup } from '@/components/nav/SidebarNavGroup'
import { readGroupOpen, writeGroupOpen } from '@/components/nav/sidebarPrefs'
import LiveClock from './noc/LiveClock'
import { ROLE_LABELS } from '@/components/settings/settingsLabels'

function SidebarNavLink({
  item,
  onNavigate,
  requestsBadge,
}: {
  item: SidebarNavItem
  onNavigate?: () => void
  requestsBadge?: number
}) {
  const Icon = item.icon
  const showRequests = item.to === '/users' && requestsBadge != null && requestsBadge > 0

  return (
    <div className="relative">
      <NavLink
        to={item.to}
        end={item.end}
        onClick={onNavigate}
        className={({ isActive }) =>
          cn(
            'orientation-compact-sidebar-link group relative flex items-center gap-3 rounded-xl px-2.5 py-2 text-sm font-medium transition-colors',
            showRequests && 'pr-12',
            isActive
              ? 'bg-primary/10 text-foreground'
              : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
          )
        }
      >
        {({ isActive }) => (
          <>
            <span
              className={cn(
                'absolute bottom-2 left-0 top-2 w-0.5 rounded-full',
                isActive ? 'bg-primary' : 'opacity-0',
              )}
              aria-hidden
            />
            <span
              className={cn(
                'orientation-compact-sidebar-link-icon flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-colors',
                isActive
                  ? 'border-primary/25 bg-primary/15 text-primary'
                  : 'border-transparent bg-muted/60 text-muted-foreground group-hover:bg-muted group-hover:text-foreground',
              )}
            >
              <Icon size={17} strokeWidth={2} />
            </span>
            <span className="min-w-0 truncate leading-snug">{item.label}</span>
            {item.badge != null && item.badge > 0 ? (
              <Badge variant="destructive" className="text-[10px] shrink-0">
                {item.badge > 9 ? '9+' : item.badge}
              </Badge>
            ) : null}
          </>
        )}
      </NavLink>
      {showRequests ? (
        <Link
          to="/users?requests=1"
          onClick={onNavigate}
          title="Заявки ждут решения"
          className="absolute right-2 top-1/2 z-10 flex h-5 min-w-5 -translate-y-1/2 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {requestsBadge > 9 ? '9+' : requestsBadge}
        </Link>
      ) : null}
    </div>
  )
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()
  const { isEnabled, loading: featuresLoading, features } = useFeatureModules()
  const { theme, toggleTheme } = useTheme()
  // Живой счётчик из общего SSE-потока: не застывает до перезагрузки страницы.
  const { pendingRequestsCount } = useNotificationCenter()
  const location = useLocation()
  // Свёрнутость групп: одна точка хранения на весь сайдбар.
  const [groupOpen, setGroupOpen] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(SIDEBAR_NAV.groups.map((group) => [group.id, readGroupOpen(group.id)])),
  )
  const [messagesUnread, setMessagesUnread] = useState(0)
  useEffect(() => {
    // Счётчик админский: обычным пользователям не опрашиваем (иначе 403 каждую минуту).
    if (user?.role !== 'admin' || !isEnabled('user_messaging')) return
    let cancelled = false
    const tick = async () => {
      if (document.hidden) return
      try {
        const { count } = await getMessageUnreadCount()
        if (!cancelled) setMessagesUnread(count)
      } catch {
        // Счётчик не критичен: страница «Сообщения» работает и без него.
      }
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 60_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [isEnabled, user?.role])
  const initials = user?.username?.slice(0, 2).toUpperCase() ?? '?'
  const profileItem: SidebarNavItem = {
    to: '/settings/personal',
    label: 'Мой профиль',
    icon: User,
    end: false,
    adminOnly: false,
    featureKey: null,
  }
  // Без кэша до загрузки модулей фильтруем пункты как выключенные: иначе на секунду
  // мигают отключённые разделы и вытесняют остальные за границу сайдбара.
  const hasCachedFeatures = Object.keys(features).length > 0
  const navFeatureEnabled = (key: string) =>
    featuresLoading && !hasCachedFeatures ? false : isEnabled(key)
  const visibleNav = getVisibleSidebarNav(user?.role, navFeatureEnabled)

  const pinnedItems = visibleNav.pinned.map((item) =>
    item.to === '/messages' ? { ...item, badge: messagesUnread } : item,
  )
  const footerItem = visibleNav.footer ?? profileItem

  // Активная группа раскрыта; вручную её можно свернуть, но переход в группу
  // снова её раскрывает. Зависимость — только набор активных id, не весь рендер.
  const activeGroupKey = visibleNav.groups
    .filter((group) => group.items.some((item) => isSidebarItemActive(item, location.pathname)))
    .map((group) => group.id)
    .join('|')

  useEffect(() => {
    if (!activeGroupKey) return
    const ids = activeGroupKey.split('|')
    setGroupOpen((prev) => {
      if (ids.every((id) => prev[id] !== false)) return prev
      const next = { ...prev }
      for (const id of ids) next[id] = true
      return next
    })
  }, [activeGroupKey, location.pathname])

  const toggleGroupOpen = (id: string, open: boolean) => {
    setGroupOpen((prev) => ({ ...prev, [id]: open }))
    writeGroupOpen(id, open)
  }

  const themeToggle = (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8 shrink-0"
      onClick={() => toggleTheme()}
      aria-label={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
    >
      {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
    </Button>
  )

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="orientation-compact-sidebar-header shrink-0 border-b border-border/60 px-3 py-4">
        <div className="flex items-center gap-3">
          <div className="orientation-compact-sidebar-brand-icon flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <Shield size={20} strokeWidth={2} />
          </div>
          <div className="min-w-0">
            <h1 className="text-sm font-semibold leading-tight">AntiZapret</h1>
            <p className="orientation-compact-sidebar-brand-sub text-xs leading-relaxed text-muted-foreground">
              NOC · VPN OPS
            </p>
          </div>
        </div>

        <div className="orientation-compact-sidebar-status mt-3 flex items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-3 py-2">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          <span className="text-xs font-medium text-emerald-700 dark:text-emerald-300">Система активна</span>
          <Radio size={13} className="ml-auto shrink-0 text-emerald-600/70 dark:text-emerald-400/70" />
        </div>
      </div>

      <nav
        className="orientation-compact-sidebar-nav flex min-h-0 flex-1 flex-col overflow-y-auto px-2 py-2"
        aria-label="Основная навигация"
      >
        <ul className="space-y-0.5">
          {pinnedItems.map((item) => (
            <li key={item.to}>
              <SidebarNavLink
                item={item}
                onNavigate={onNavigate}
                requestsBadge={pendingRequestsCount}
              />
            </li>
          ))}
        </ul>

        {visibleNav.groups.map((group, index) => {
          const open = groupOpen[group.id] ?? group.defaultOpen ?? true
          return (
            <div key={group.id} className={cn(index > 0 && 'mt-1 border-t border-border/40 pt-1')}>
              <SidebarNavGroup
                id={group.id}
                label={group.label}
                open={open}
                onToggle={() => toggleGroupOpen(group.id, !open)}
              >
                {group.items.map((item) => (
                  <li key={item.to}>
                    <SidebarNavLink item={item} onNavigate={onNavigate} />
                  </li>
                ))}
              </SidebarNavGroup>
            </div>
          )
        })}

        <div className="mt-auto border-t border-border/40 pt-1">
          <SidebarNavLink item={footerItem} onNavigate={onNavigate} />
        </div>
      </nav>

      <div className="orientation-compact-sidebar-footer shrink-0 border-t border-border/60 bg-card p-3 pb-safe">
        <div className="orientation-compact-sidebar-footer-stack space-y-2">
          <div className="flex items-center justify-between rounded-lg bg-muted/30 px-2 py-1.5">
            <LiveClock />
            {themeToggle}
          </div>

          <div className="flex items-center gap-3 rounded-xl border border-border/80 bg-muted/20 p-2.5">
            <Avatar className="h-9 w-9 shrink-0">
              <AvatarFallback className="bg-primary/15 text-xs font-semibold text-primary">{initials}</AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium leading-tight">{user?.username}</p>
              <p className="text-xs text-muted-foreground">
                {user?.role ? ROLE_LABELS[user.role] : '—'}
              </p>
            </div>
          </div>

          <Button
            variant="ghost"
            className="w-full justify-start gap-2 text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={logout}
          >
            <LogOut size={16} />
            Выйти
          </Button>
          <a
            href={DOCS.index}
            target="_blank"
            rel="noopener noreferrer"
            className="block px-1 text-center text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            Руководства
          </a>
          <a
            href={FEEDBACK_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="block px-1 pb-1 text-center text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            Обратная связь
          </a>
        </div>

        <div className="orientation-compact-sidebar-footer-inline hidden items-center gap-2">
          <Avatar className="h-8 w-8 shrink-0">
            <AvatarFallback className="bg-primary/15 text-xs font-semibold text-primary">{initials}</AvatarFallback>
          </Avatar>
          <p className="min-w-0 flex-1 truncate text-sm font-medium">{user?.username}</p>
          {themeToggle}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={logout}
            aria-label="Выйти"
          >
            <LogOut size={16} />
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function Layout() {
  const { user } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex min-h-dscreen bg-background">
      <HaScopeEnforcer />
      <aside className="hidden h-dscreen w-72 shrink-0 overflow-hidden border-r border-border/80 bg-card lg:sticky lg:top-0 lg:block">
        <SidebarContent />
      </aside>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent
          side="left"
          className="orientation-compact-sidebar-sheet flex h-dscreen max-h-dscreen w-72 flex-col overflow-hidden p-0"
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Навигация</SheetTitle>
            <SheetDescription>Меню разделов панели</SheetDescription>
          </SheetHeader>
          <SidebarContent onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-4 border-b bg-background px-4 pt-safe lg:px-6 lg:pt-0 orientation-compact-header">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)}>
            <Menu size={20} />
          </Button>
          <div className="min-w-0 flex-1">
            <p className="orientation-compact-header-subtitle text-xs text-muted-foreground">Network Operations Center</p>
            <h1 className="truncate text-sm font-semibold leading-tight">AntiZapret VPN</h1>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            <div className="sm:hidden">
              <NodeSelector compact />
            </div>
            <div className="hidden sm:block">
              <NodeSelector />
            </div>
            {/* Один экземпляр: два колокола давали дубли тостов и SSE. */}
            <NotificationBell />
            <span className="mono hidden text-xs text-muted-foreground sm:inline">
              SESS · {user?.username?.toUpperCase()}
            </span>
            <span className="orientation-compact-header-subtitle hidden sm:inline">
              <LiveClock />
            </span>
          </div>
        </header>

        <main className="flex-1 p-4 lg:p-6">
          <ActiveNodeChangedBanner />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
