import { useState } from 'react'
import { Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useNotificationCenter } from '@/context/NotificationCenterContext'
import NotificationPopover from './NotificationPopover'

function bellBadge(unreadCount: number) {
  if (unreadCount <= 0) return null
  // Число уже входит в aria-label кнопки-колокола: визуальный бейдж не дублируем скринридеру.
  return (
    <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center" aria-hidden>
      <Badge variant="destructive" className="px-1.5 text-[10px]">
        {unreadCount > 9 ? '9+' : unreadCount}
      </Badge>
    </span>
  )
}

export default function NotificationBell() {
  const { bellItems, counts, unreadCount, markAllRead, setState, bellLoading, bellError, refetchBell } =
    useNotificationCenter()
  const [desktopOpen, setDesktopOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  const bellLabel = unreadCount > 0 ? `Уведомления, непрочитанных: ${unreadCount}` : 'Уведомления'
  const markRead = (id: number) => void setState(id, { read: true })

  return (
    <>
      {/* Desktop: dropdown next to NodeSelector / LiveClock. */}
      <div className="hidden items-center gap-2 sm:flex">
        <DropdownMenu
          open={desktopOpen}
          onOpenChange={(open) => {
            // Каждое открытие — свежее превью и актуальный счётчик в шапке.
            setDesktopOpen(open)
            if (open) void refetchBell()
          }}
        >
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="relative h-8 w-8 shrink-0"
              aria-label={bellLabel}
            >
              <Bell size={18} />
              {bellBadge(unreadCount)}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            sideOffset={6}
            className="w-96 max-w-[min(24rem,calc(100vw-1.5rem))] p-0"
            aria-label="Уведомления"
            onCloseAutoFocus={(event) => event.preventDefault()}
          >
            <NotificationPopover
              open={desktopOpen}
              onOpenChange={setDesktopOpen}
              items={bellItems}
              counts={counts}
              bellLoading={bellLoading}
              bellError={bellError}
              onRetry={() => void refetchBell()}
              onMarkAllRead={() => void markAllRead()}
              onMarkRead={markRead}
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
          aria-label={bellLabel}
          onClick={() => {
            setMobileOpen(true)
            void refetchBell()
          }}
        >
          <Bell size={18} />
          {bellBadge(unreadCount)}
        </Button>
        <NotificationPopover
          open={mobileOpen}
          onOpenChange={setMobileOpen}
          sheet
          items={bellItems}
          counts={counts}
          bellLoading={bellLoading}
          bellError={bellError}
          onRetry={() => void refetchBell()}
          onMarkAllRead={() => void markAllRead()}
          onMarkRead={markRead}
        />
      </div>
    </>
  )
}
