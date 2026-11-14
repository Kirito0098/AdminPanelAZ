import { NavLink } from 'react-router-dom'
import { BellOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import type { NotificationCounts, NotificationItem } from '@/api/notifications'
import { BELL_PREVIEW_LIMIT } from '@/context/NotificationCenterContext'
import { pluralRu } from '@/lib/plural'
import { cn } from '@/lib/utils'
import NotificationCard from './NotificationCard'
import { isSnoozed } from './time'

interface NotificationPopoverProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sheet?: boolean
  /** Превью колокола: последние уведомления, включая прочитанные. */
  items: NotificationItem[]
  counts: NotificationCounts
  /** Идёт первая загрузка превью (при пустом списке показываем скелетоны). */
  bellLoading: boolean
  /** Запрос превью упал — при пустом списке предлагаем повторить. */
  bellError: boolean
  onRetry: () => void
  onMarkAllRead: () => void
  onMarkRead: (id: number) => void
}

export default function NotificationPopover({
  open,
  onOpenChange,
  sheet = false,
  items,
  counts,
  bellLoading,
  bellError,
  onRetry,
  onMarkAllRead,
  onMarkRead,
}: NotificationPopoverProps) {
  // Отложенные в панель не попадают: они вернутся, когда созреют.
  const visible = items.filter((item) => !isSnoozed(item.state.snoozed_until))
  // Непрочитанные выше прочитанных; внутри групп порядок исходный (id DESC).
  const sorted = [...visible]
    .sort((a, b) => Number(a.state.read) - Number(b.state.read))
    .slice(0, BELL_PREVIEW_LIMIT)
  const shownUnread = sorted.filter((item) => !item.state.read && !item.state.hidden).length
  const moreUnread = Math.max(0, counts.unread - shownUnread)

  const historyLink = (label: string) => (
    <NavLink
      to="/monitoring?tab=logs&log=notifications"
      className="text-xs text-primary underline-offset-4 hover:underline"
      onClick={() => onOpenChange(false)}
    >
      {label}
    </NavLink>
  )

  const moreUnreadLabel =
    moreUnread > 0
      ? `Ещё ${moreUnread} ${pluralRu(moreUnread, ['непрочитанное', 'непрочитанных', 'непрочитанных'])} →`
      : ''

  // Пустой список: сначала загрузка, затем ошибка, иначе «пусто».
  const emptyState = bellLoading ? (
    <>
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-16 w-full rounded-xl" />
      <Skeleton className="h-16 w-full rounded-xl" />
    </>
  ) : bellError ? (
    <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
      <span>Не удалось загрузить</span>
      <Button variant="outline" size="sm" onClick={onRetry}>
        Повторить
      </Button>
    </div>
  ) : (
    <div className="flex flex-col items-center gap-1 py-8 text-center text-sm text-muted-foreground">
      <BellOff size={24} />
      <span>{counts.unread > 0 ? 'Свежих уведомлений нет' : 'Уведомлений пока нет'}</span>
      <span className="text-xs">
        {counts.unread > 0 ? 'Непрочитанные — глубже в истории' : 'Здесь появятся события панели'}
      </span>
      {moreUnreadLabel && historyLink(moreUnreadLabel)}
    </div>
  )

  const body = (
    <div className={cn('flex flex-col', sheet && 'min-h-0 flex-1')}>
      {(!sheet || counts.unread > 0) && (
        <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-muted/50 px-3 py-2">
          {!sheet && (
            <div className="flex min-w-0 items-center gap-2">
              <span className="text-sm font-semibold">Уведомления</span>
              {counts.unread > 0 && (
                <Badge
                  variant="secondary"
                  role="status"
                  aria-label={`Непрочитанных: ${counts.unread}`}
                >
                  {counts.unread}
                </Badge>
              )}
            </div>
          )}
          {counts.unread > 0 && (
            <Button
              variant="outline"
              size="sm"
              className={sheet ? 'ml-auto' : undefined}
              onClick={onMarkAllRead}
            >
              Прочитать все
            </Button>
          )}
        </div>
      )}

      <div
        className={cn(
          'flex flex-col gap-2 overflow-y-auto p-2',
          sheet ? 'min-h-0 flex-1' : 'max-h-[52vh]',
        )}
      >
        {sorted.length === 0 ? (
          emptyState
        ) : (
          <>
            {bellError && (
              <div className="flex items-center justify-between gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-xs text-destructive">
                <span>Не удалось обновить</span>
                <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={onRetry}>
                  Повторить
                </Button>
              </div>
            )}
            {sorted.map((item) => (
              <NotificationCard
                key={item.id}
                item={item}
                compact
                onMarkRead={onMarkRead}
                onNavigate={() => onOpenChange(false)}
              />
            ))}
            {moreUnreadLabel && historyLink(moreUnreadLabel)}
          </>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-border/60 px-3 py-2">
        {historyLink('Вся история →')}
        {counts.attention > 0 && (
          <span className="text-[11px] text-destructive">{counts.attention} требует внимания</span>
        )}
      </div>
    </div>
  )

  if (sheet) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="flex w-96 flex-col p-0">
          <SheetHeader className="px-4 pb-2">
            <SheetTitle>Уведомления</SheetTitle>
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
