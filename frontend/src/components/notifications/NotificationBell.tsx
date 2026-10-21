import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotificationCenter } from '@/context/NotificationCenterContext'
import type { NotificationItem } from '@/api/notifications'
import NotificationPopover from './NotificationPopover'

function pathForNotification(item: NotificationItem): string | null {
  if (item.action_payload) {
    const requestId = item.action_payload.request_id
    if (
      item.event_type.startsWith('access_request_') &&
      typeof requestId === 'number' &&
      Number.isFinite(requestId)
    ) {
      return `/users?request=${requestId}`
    }
  }
  if (item.event_type.startsWith('access_request_') || item.category === 'requests') {
    return '/users?requests=1'
  }
  if (item.category === 'security') return '/logs'
  if (item.category === 'nodes') return '/nodes'
  return null
}

type TabKey = 'all' | 'requests' | 'security' | 'nodes' | 'services' | 'tasks'

function bellBadge(unreadCount: number) {
  if (unreadCount <= 0) return null
  return (
    <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center">
      <Badge variant="destructive" className="text-[10px] px-1.5">
        {unreadCount > 9 ? '9+' : unreadCount}
      </Badge>
    </span>
  )
}

export default function NotificationBell() {
  const navigate = useNavigate()
  const { isEnabled } = useFeatureModules()
  const {
    items,
    unreadCount,
    pendingRequestsCount,
    category,
    setCategory,
    markAllRead,
    markReadUpTo,
  } = useNotificationCenter()
  const requestsTabEnabled = isEnabled('user_provisioning')

  const [desktopOpen, setDesktopOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  // Открыли центр уведомлений — считаем ленту просмотренной и гасим бейдж.
  // Иначе непрочитанные копятся и «1 новая заявка» выглядит как «8 новых».
  useEffect(() => {
    if ((desktopOpen || mobileOpen) && unreadCount > 0) {
      void markAllRead()
    }
  }, [desktopOpen, mobileOpen, unreadCount, markAllRead])

  const handleItemClick = useCallback(
    (item: NotificationItem) => {
      const path = pathForNotification(item)
      if (!path) return
      setDesktopOpen(false)
      setMobileOpen(false)
      void markReadUpTo(item.id)
      navigate(path)
    },
    [navigate, markReadUpTo],
  )

  const activeCategory: TabKey = category === 'requests' && !requestsTabEnabled ? 'all' : category

  return (
    <>
      {/* Desktop: dropdown next to NodeSelector / LiveClock. */}
      <div className="hidden sm:flex items-center gap-2">
        <DropdownMenu open={desktopOpen} onOpenChange={setDesktopOpen}>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="relative h-8 w-8 shrink-0" aria-label="Уведомления">
              <Bell size={18} />
              {bellBadge(unreadCount)}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            sideOffset={6}
            className="w-96 max-w-[min(24rem,calc(100vw-1.5rem))] p-0"
            onCloseAutoFocus={(e) => e.preventDefault()}
          >
            <NotificationPopover
              open={desktopOpen}
              onOpenChange={setDesktopOpen}
              sheet={false}
              items={items}
              unreadCount={unreadCount}
              pendingRequestsCount={pendingRequestsCount}
              category={activeCategory}
              onCategoryChange={setCategory}
              onMarkAllRead={markAllRead}
              onItemClick={handleItemClick}
            />
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Mobile: drawer/sheet next to compact NodeSelector. */}
      <div className="flex items-center gap-2 sm:hidden">
        <Button
          variant="ghost"
          size="icon"
          className="relative h-8 w-8 shrink-0"
          aria-label="Уведомления"
          onClick={() => setMobileOpen(true)}
        >
          <Bell size={18} />
          {bellBadge(unreadCount)}
        </Button>
        <NotificationPopover
          open={mobileOpen}
          onOpenChange={setMobileOpen}
          sheet
          items={items}
          unreadCount={unreadCount}
          pendingRequestsCount={pendingRequestsCount}
          category={activeCategory}
          onCategoryChange={setCategory}
          onMarkAllRead={markAllRead}
          onItemClick={handleItemClick}
        />
      </div>
    </>
  )
}

