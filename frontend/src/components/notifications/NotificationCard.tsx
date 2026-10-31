import { useNavigate } from 'react-router-dom'
import { Bell, Check, MoreHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { formatDate } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { NotificationItem } from '@/api/notifications'
import { CATEGORY_ICON, categoryLabel } from './labels'
import { pathForNotification } from './paths'
import { SNOOZE_PRESETS, formatRelative, isSnoozed, type SnoozePreset } from './time'

interface NotificationCardProps {
  item: NotificationItem
  /** В колоколе только «прочитать» и переход — без откладывания и скрытия. */
  compact?: boolean
  onMarkRead: (id: number) => void
  onSnooze?: (id: number, preset: SnoozePreset) => void
  onHide?: (id: number) => void
  onRestore?: (id: number) => void
  onNavigate?: () => void
}

const STRIP_CLASS: Record<string, string> = {
  error: 'bg-destructive',
  warning: 'bg-amber-500',
}

export default function NotificationCard({
  item,
  compact = false,
  onMarkRead,
  onSnooze,
  onHide,
  onRestore,
  onNavigate,
}: NotificationCardProps) {
  const navigate = useNavigate()
  const Icon = CATEGORY_ICON[item.category] ?? Bell
  const snoozed = isSnoozed(item.state.snoozed_until)
  const unread = !item.state.read && !item.state.hidden && !snoozed
  const target = pathForNotification(item)
  const dimmed = snoozed || item.state.hidden

  const open = () => {
    if (!target) return
    onNavigate?.()
    navigate(target)
  }

  return (
    <article
      className={cn(
        'relative flex gap-3 rounded-xl border border-border/70 bg-card p-3 transition-colors',
        unread && 'border-primary/25 bg-primary/[0.04]',
        dimmed && 'opacity-60',
        target && 'cursor-pointer hover:bg-muted/40',
      )}
      onClick={open}
      role={target ? 'button' : undefined}
      tabIndex={target ? 0 : undefined}
      onKeyDown={(event) => {
        if (!target) return
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          open()
        }
      }}
    >
      <span
        className={cn(
          'absolute bottom-3 left-0 top-3 w-[3px] rounded-full bg-border',
          STRIP_CLASS[item.level] ?? (snoozed ? 'bg-amber-500' : 'bg-border'),
        )}
        aria-hidden
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1 pl-1.5">
        <div className="flex items-start gap-2">
          {unread && (
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-label="Непрочитано" />
          )}
          <Icon size={14} className="mt-0.5 shrink-0 text-muted-foreground" aria-hidden />
          <h3 className="min-w-0 flex-1 text-sm font-semibold leading-snug">{item.title}</h3>
          <span className="shrink-0 text-[11px] text-muted-foreground">{formatRelative(item.created_at)}</span>
        </div>
        {item.details.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {item.details.map((detail) => (
              <span
                key={`${detail.label}-${detail.value}`}
                className="inline-flex max-w-full items-baseline gap-1 rounded-md border border-border/60 bg-muted/50 px-1.5 py-0.5 text-[11px] leading-tight"
              >
                <span className="shrink-0 text-muted-foreground/80">{detail.label}</span>
                <span className="truncate font-semibold text-foreground">{detail.value}</span>
              </span>
            ))}
          </div>
        ) : item.message ? (
          <p className="line-clamp-2 text-xs text-muted-foreground">{item.message}</p>
        ) : null}
        <p className="text-[11px] text-muted-foreground/70">
          {categoryLabel(item.category)}
          {snoozed && item.state.snoozed_until
            ? ` · отложено до ${formatDate(item.state.snoozed_until, { hour: '2-digit', minute: '2-digit' })}`
            : ''}
          {item.state.hidden ? ' · скрыто' : ''}
        </p>
      </div>

      {compact ? (
        !item.state.read && (
          // В колоколе живёт внешнее Radix-меню: вложенное меню оно закрывает вместе с собой,
          // поэтому здесь одна явная кнопка. Отложить и скрыть — на странице уведомлений.
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            aria-label="Отметить прочитанным"
            onClick={(event) => {
              event.stopPropagation()
              onMarkRead(item.id)
            }}
          >
            <Check size={16} />
          </Button>
        )
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0"
              aria-label="Действия с уведомлением"
              onClick={(event) => event.stopPropagation()}
            >
              <MoreHorizontal size={16} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" onClick={(event) => event.stopPropagation()}>
            {!item.state.read && (
              <DropdownMenuItem onSelect={() => onMarkRead(item.id)}>Отметить прочитанным</DropdownMenuItem>
            )}
            {target && <DropdownMenuItem onSelect={open}>Перейти</DropdownMenuItem>}
            {onSnooze && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  Отложить
                </DropdownMenuLabel>
                {SNOOZE_PRESETS.map((preset) => (
                  <DropdownMenuItem key={preset.id} onSelect={() => onSnooze(item.id, preset.id)}>
                    {preset.label}
                  </DropdownMenuItem>
                ))}
              </>
            )}
            {onHide && !item.state.hidden && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => onHide(item.id)}>Скрыть</DropdownMenuItem>
              </>
            )}
            {onRestore && item.state.hidden && (
              <DropdownMenuItem onSelect={() => onRestore(item.id)}>Вернуть в ленту</DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </article>
  )
}
