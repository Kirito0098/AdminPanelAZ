import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
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
  LogOut,
  Menu,
  Moon,
  Radio,
  Send,
  Server,
  Settings2,
  Shield,
  Sun,
  User,
} from 'lucide-react'
import NodeSelector from '@/components/NodeSelector'
import HaScopeEnforcer from '@/components/HaScopeEnforcer'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useTheme } from '@/context/ThemeContext'
import ForcePasswordChange from './ForcePasswordChange'
import LiveClock from './noc/LiveClock'
import SettingsSidebarSection from '@/components/settings/SettingsSidebarSection'
import { ROLE_LABELS } from '@/components/settings/settingsLabels'

type NavItemDef = {
  to: string
  label: string
  icon: LucideIcon
  end: boolean
  adminOnly: boolean
  viewerOk: boolean
  featureKey: string | null
  featureAnyOf?: readonly string[]
}

type NavGroupDef = {
  label: string
  items: NavItemDef[]
}

const NAV_GROUPS: NavGroupDef[] = [
  {
    label: 'Операции',
    items: [
      { to: '/', label: 'Конфигурации', icon: LayoutDashboard, end: true, adminOnly: false, viewerOk: true, featureKey: null },
      { to: '/monitoring', label: 'NOC Мониторинг', icon: Activity, end: false, adminOnly: true, viewerOk: false, featureKey: 'logs_dashboard' },
      { to: '/traffic', label: 'Мониторинг трафика', icon: HardDrive, end: false, adminOnly: false, viewerOk: true, featureKey: 'traffic_sync' },
      { to: '/routing', label: 'Маршрутизация / CIDR', icon: GitBranch, end: false, adminOnly: true, viewerOk: false, featureKey: 'routing' },
    ],
  },
  {
    label: 'Конфигурация',
    items: [
      { to: '/antizapret', label: 'Конфиг AntiZapret', icon: Settings2, end: false, adminOnly: true, viewerOk: false, featureKey: 'routing' },
      { to: '/warper', label: 'AZ-WARP', icon: Globe, end: false, adminOnly: true, viewerOk: false, featureKey: 'warper' },
      { to: '/telegram', label: 'Telegram', icon: Send, end: false, adminOnly: true, viewerOk: false, featureKey: 'telegram' },
      { to: '/edit-files', label: 'Редактор файлов', icon: FileText, end: false, adminOnly: true, viewerOk: false, featureKey: 'edit_files' },
    ],
  },
  {
    label: 'Система',
    items: [
      {
        to: '/logs',
        label: 'Журналы',
        icon: ClipboardList,
        end: false,
        adminOnly: true,
        viewerOk: false,
        featureKey: null,
        featureAnyOf: ['logs_dashboard', 'action_logs'] as const,
      },
      { to: '/server-monitor', label: 'Сервер', icon: Cpu, end: false, adminOnly: true, viewerOk: false, featureKey: 'server_monitor' },
      { to: '/nodes', label: 'Узлы', icon: Server, end: false, adminOnly: true, viewerOk: false, featureKey: null },
    ],
  },
]

function isNavItemVisible(
  item: NavItemDef,
  userRole: string | undefined,
  isEnabled: (key: string) => boolean,
): boolean {
  if (item.featureAnyOf?.length) {
    if (!item.featureAnyOf.some((key) => isEnabled(key))) return false
  } else if (item.featureKey && !isEnabled(item.featureKey)) {
    return false
  }
  if (userRole === 'viewer') return item.viewerOk
  if (item.adminOnly) return userRole === 'admin'
  return true
}

function NavGroupHeader({ label }: { label: string }) {
  return (
    <p className="orientation-compact-sidebar-group-label px-3 pb-1 pt-3 text-xs font-medium text-muted-foreground first:pt-1">
      {label}
    </p>
  )
}

function SidebarNavLink({
  item,
  onNavigate,
}: {
  item: NavItemDef
  onNavigate?: () => void
}) {
  const Icon = item.icon

  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'orientation-compact-sidebar-link group relative flex items-center gap-3 rounded-xl px-2.5 py-2 text-sm font-medium transition-colors',
          isActive
            ? 'bg-primary/10 text-foreground ring-1 ring-primary/20'
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
        </>
      )}
    </NavLink>
  )
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()
  const { isEnabled } = useFeatureModules()
  const { theme, toggleTheme } = useTheme()
  const initials = user?.username?.slice(0, 2).toUpperCase() ?? '?'
  const isAdmin = user?.role === 'admin'

  const visibleGroups = NAV_GROUPS.map((group) => {
    const items = group.items.filter((item) => isNavItemVisible(item, user?.role, isEnabled))
    if (group.label === 'Система' && !isAdmin) {
      items.push({
        to: '/settings/personal',
        label: 'Мой профиль',
        icon: User,
        end: false,
        adminOnly: false,
        viewerOk: true,
        featureKey: null,
      })
    }
    return { ...group, items }
  }).filter((group) => group.items.length > 0 || (group.label === 'Система' && isAdmin))

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
        {visibleGroups.map((group) => (
          <div key={group.label}>
            <NavGroupHeader label={group.label} />
            <ul className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.to}>
                  <SidebarNavLink item={item} onNavigate={onNavigate} />
                </li>
              ))}
              {group.label === 'Система' && isAdmin && <SettingsSidebarSection onNavigate={onNavigate} />}
            </ul>
          </div>
        ))}
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
      <ForcePasswordChange />
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
          <div className="shrink-0 sm:hidden">
            <NodeSelector compact />
          </div>
          <div className="hidden items-center gap-3 sm:flex">
            <NodeSelector />
            <span className="mono text-xs text-muted-foreground">SESS · {user?.username?.toUpperCase()}</span>
            <span className="orientation-compact-header-subtitle">
              <LiveClock />
            </span>
          </div>
        </header>

        <main className="flex-1 overflow-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
