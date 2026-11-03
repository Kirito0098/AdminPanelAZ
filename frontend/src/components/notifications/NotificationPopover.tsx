import { NavLink } from 'react-router-dom'
import { BellOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { NotificationCounts, NotificationItem } from '@/api/notifications'
import NotificationCard from './NotificationCard'

export interface NotificationPopoverProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sheet?: boolean
  /** Только непрочитанные: список для колокола готовит NotificationCenterContext. */
  items: NotificationItem[]
  counts: NotificationCounts
  onMarkAllRead: () => void
  onMarkRead: (id: number) => void
}

export default function NotificationPopover({
  open,
  onOpenChange,
  sheet = false,
  items,
  counts,
  onMarkAllRead,
  onMarkRead,
}: NotificationPopoverProps) {
  const body = (
    <div className="flex flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-muted/50 px-3 py-2">
        <span className="text-xs font-semibold">
          {counts.unread > 0 ? `${counts.unread} новых` : 'Центр уведомлений'}
        </span>
        <Button variant="outline" size="sm" onClick={onMarkAllRead} disabled={!items.length}>
          Отметить всё
        </Button>
      </div>

      <div className="flex max-h-[52vh] flex-col gap-2 overflow-y-auto p-2">
        {items.length === 0 ? (
          <div className="flex flex-col items-center gap-1 py-8 text-center text-sm text-muted-foreground">
            <BellOff size={20} />
            <span>Новых уведомлений нет</span>
            <span className="text-xs">Прочитанные — в истории ниже</span>
          </div>
        ) : (
          items.map((item) => (
            <NotificationCard
              key={item.id}
              item={item}
              compact
              onMarkRead={onMarkRead}
              onNavigate={() => onOpenChange(false)}
            />
          ))
        )}
      </div>

      <div className="flex items-center justify-between border-t border-border/60 px-3 py-2">
        <NavLink
          to="/logs?tab=notifications"
          className="text-xs text-primary underline-offset-4 hover:underline"
          onClick={() => onOpenChange(false)}
        >
          Вся история →
        </NavLink>
        {counts.attention > 0 && (
          <span className="text-[11px] text-destructive">{counts.attention} требует внимания</span>
        )}
      </div>
    </div>
  )

  if (sheet) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="w-96 p-0">
          <SheetHeader className="px-4 pb-2">
            <SheetTitle>Центр уведомлений</SheetTitle>
            <SheetDescription className="text-xs">
              Непрочитано: <span className="font-semibold">{counts.unread}</span>
              {counts.snoozed > 0 ? ` · отложено: ${counts.snoozed}` : ''}
            </SheetDescription>
          </SheetHeader>
          {body}
        </SheetContent>
      </Sheet>
    )
  }

  return <div className="w-full">{body}</div>
}
