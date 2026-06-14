import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
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
  Settings,
  Settings2,
  Shield,
  Sun,
} from 'lucide-react'
import NodeSelector from '@/components/NodeSelector'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useTheme } from '@/context/ThemeContext'
import ForcePasswordChange from './ForcePasswordChange'
import LiveClock from './noc/LiveClock'

const baseNavItems: Array<{
  to: string
  label: string
  icon: typeof LayoutDashboard
  end: boolean
  adminOnly: boolean
  viewerOk: boolean
  featureKey: string | null
  featureAnyOf?: readonly string[]
}> = [
  { to: '/', label: 'Конфигурации', icon: LayoutDashboard, end: true, adminOnly: false, viewerOk: true, featureKey: null },
  { to: '/monitoring', label: 'NOC Мониторинг', icon: Activity, end: false, adminOnly: false, viewerOk: true, featureKey: 'logs_dashboard' },
  { to: '/traffic', label: 'Мониторинг трафика', icon: HardDrive, end: false, adminOnly: false, viewerOk: true, featureKey: 'traffic_sync' },
  { to: '/routing', label: 'Маршрутизация / CIDR', icon: GitBranch, end: false, adminOnly: false, viewerOk: true, featureKey: 'routing' },
  { to: '/antizapret', label: 'Конфиг AntiZapret', icon: Settings2, end: false, adminOnly: true, viewerOk: false, featureKey: 'routing' },
  { to: '/warper', label: 'AZ-WARP', icon: Globe, end: false, adminOnly: true, viewerOk: false, featureKey: 'warper' },
  { to: '/telegram', label: 'Telegram', icon: Send, end: false, adminOnly: true, viewerOk: false, featureKey: 'telegram' },
  { to: '/edit-files', label: 'Редактор файлов', icon: FileText, end: false, adminOnly: false, viewerOk: false, featureKey: 'edit_files' },
  { to: '/logs', label: 'Журналы', icon: ClipboardList, end: false, adminOnly: false, viewerOk: true, featureKey: null, featureAnyOf: ['logs_dashboard', 'action_logs'] as const },
  { to: '/server-monitor', label: 'Сервер', icon: Cpu, end: false, adminOnly: true, viewerOk: false, featureKey: 'server_monitor' },
  { to: '/nodes', label: 'Узлы', icon: Server, end: false, adminOnly: true, viewerOk: false, featureKey: null },
  { to: '/settings', label: 'Настройки', icon: Settings, end: false, adminOnly: false, viewerOk: true, featureKey: null },
]

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()
  const { isEnabled } = useFeatureModules()
  const { theme, toggleTheme } = useTheme()
  const initials = user?.username?.slice(0, 2).toUpperCase() ?? '?'

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-2 py-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Shield size={20} />
        </div>
        <div>
          <h1 className="text-sm font-bold tracking-tight">AntiZapret</h1>
          <p className="text-xs text-muted-foreground">NOC · VPN OPS</p>
        </div>
      </div>

      <div className="mx-2 mb-4 flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-600 dark:text-emerald-400">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
        </span>
        Система активна
        <Radio size={12} className="ml-auto opacity-60" />
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-2">
        {baseNavItems
          .filter((item) => {
            if ('featureAnyOf' in item && item.featureAnyOf?.length) {
              if (!item.featureAnyOf.some((key) => isEnabled(key))) return false
            } else if (item.featureKey && !isEnabled(item.featureKey)) return false
            if (user?.role === 'viewer') return item.viewerOk
            if (item.adminOnly) return user?.role === 'admin'
            return true
          })
          .map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )
            }
          >
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto space-y-3 p-2">
        <Separator />
        <div className="flex items-center justify-between px-1">
          <LiveClock />
          <Button variant="ghost" size="sm" onClick={() => toggleTheme()}>
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </Button>
        </div>

        <div className="flex items-center gap-3 rounded-lg border bg-muted/50 p-3">
          <Avatar className="h-9 w-9">
            <AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">{initials}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{user?.username}</p>
            <p className="text-xs text-muted-foreground">
              {user?.role === 'admin' ? 'Администратор' : 'Оператор'}
            </p>
          </div>
        </div>

        <Button variant="outline" className="w-full border-destructive/30 text-destructive hover:bg-destructive/10" onClick={logout}>
          <LogOut size={16} />
          Выйти
        </Button>
      </div>
    </div>
  )
}

export default function Layout() {
  const { user } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex min-h-screen bg-background">
      <ForcePasswordChange />
      <aside className="hidden w-64 shrink-0 border-r bg-card lg:block">
        <SidebarContent />
      </aside>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 p-4">
          <SheetHeader className="sr-only">
            <SheetTitle>Навигация</SheetTitle>
          </SheetHeader>
          <SidebarContent onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-4 border-b bg-background/95 px-4 backdrop-blur lg:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)}>
            <Menu size={20} />
          </Button>
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Network Operations Center</p>
            <h1 className="truncate text-sm font-semibold">AntiZapret VPN</h1>
          </div>
          <div className="hidden items-center gap-3 sm:flex">
            <NodeSelector />
            <span className="mono text-xs text-muted-foreground">SESS · {user?.username?.toUpperCase()}</span>
            <LiveClock />
          </div>
        </header>

        <main className="flex-1 overflow-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
