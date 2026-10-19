import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import {
  fetchNotifications,
  markNotificationsRead,
  openNotificationsStream,
  type NotificationItem,
} from '@/api/notifications'
import NotificationPopover from './NotificationPopover'

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
  const { isEnabled } = useFeatureModules()
  const { info } = useNotifications()
  const requestsTabEnabled = isEnabled('user_provisioning')

  const [open, setOpen] = useState(false)
  const [category, setCategory] = useState<TabKey>('all')
  const [items, setItems] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [pendingRequestsCount, setPendingRequestsCount] = useState(0)
  const streamRef = useRef<ReturnType<typeof openNotificationsStream> | null>(null)
  const prevPendingRef = useRef(pendingRequestsCount)

  const refetch = useCallback(async () => {
    try {
      const data = await fetchNotifications({
        ...(category === 'all' ? {} : { category }),
        limit: 100,
      })
      setItems(data.items)
      setUnreadCount(data.unread_count)
      const pending = data.pending_requests_count
      setPendingRequestsCount(pending)
      if (
        pending > prevPendingRef.current &&
        prevPendingRef.current >= 0 &&
        (category === 'all' || category === 'requests')
      ) {
        info(`Новых заявок на доступ: ${pending - prevPendingRef.current}`)
      }
      prevPendingRef.current = pending
    } catch {
      // Keep stale data; the stream keeps reconnecting and refetching.
    }
  }, [category, info])

  useEffect(() => {
    void refetch()
    streamRef.current = openNotificationsStream((_data) => {
      void refetch()
    })
    const onFocus = () => void refetch()
    window.addEventListener('focus', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
      streamRef.current?.close()
    }
  }, [refetch])

  const handleMarkAllRead = async () => {
    if (!items.length) return
    const maxId = Math.max(...items.map((item) => item.id))
    await markNotificationsRead(maxId)
    setUnreadCount(0)
    void refetch()
  }

  const activeCategory: TabKey = category === 'requests' && !requestsTabEnabled ? 'all' : category

  return (
    <>
      {/* Desktop: popover next to NodeSelector / LiveClock. */}
      <div className="hidden sm:flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="relative h-8 w-8 shrink-0" aria-label="Уведомления">
              <Bell size={18} />
              {bellBadge(unreadCount)}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" sideOffset={6}>
            <NotificationPopover
              open={open}
              onOpenChange={setOpen}
              sheet={false}
              items={items}
              unreadCount={unreadCount}
              pendingRequestsCount={pendingRequestsCount}
              category={activeCategory}
              onCategoryChange={(key) => {
                setCategory(key)
                setOpen(false)
              }}
              onMarkAllRead={handleMarkAllRead}
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
          onClick={() => setOpen(true)}
        >
          <Bell size={18} />
          {bellBadge(unreadCount)}
        </Button>
        <NotificationPopover
          open={open}
          onOpenChange={setOpen}
          sheet
          items={items}
          unreadCount={unreadCount}
          pendingRequestsCount={pendingRequestsCount}
          category={activeCategory}
          onCategoryChange={setCategory}
          onMarkAllRead={handleMarkAllRead}
        />
      </div>
    </>
  )
}
