import type { ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/** Compact section toolbar — title, optional count, meta line, trailing actions. */
export function SettingsToolbar({
  title,
  count,
  meta,
  actions,
  className,
}: {
  title: string
  count?: number | string
  meta?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between',
        className,
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-semibold tracking-tight">{title}</h3>
          {count != null && count !== '' ? (
            <Badge variant="secondary" className="tabular-nums">
              {count}
            </Badge>
          ) : null}
        </div>
        {meta ? <div className="mt-1 text-xs text-muted-foreground">{meta}</div> : null}
      </div>
      {actions ? (
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
          {actions}
        </div>
      ) : null}
    </div>
  )
}

/** Quiet bordered panel for primary content blocks (no accent stripe). */
export function SettingsPanel({
  children,
  className,
  padded = true,
}: {
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <div className={cn('rounded-lg border bg-card shadow-sm', className)}>
      <div className={cn(padded && 'p-4')}>{children}</div>
    </div>
  )
}

/** Secondary / advanced block — collapses to keep primary surface clean. */
export function SettingsCollapsible({
  open,
  onOpenChange,
  title,
  description,
  icon,
  children,
  className,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  icon?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('rounded-lg border bg-muted/20', className)}>
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <div className="flex min-w-0 items-start gap-2.5">
          {icon ? <span className="mt-0.5 shrink-0 text-muted-foreground">{icon}</span> : null}
          <div className="min-w-0">
            <p className="text-sm font-medium">{title}</p>
            {description ? (
              <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
            ) : null}
          </div>
        </div>
        <ChevronDown
          size={16}
          className={cn(
            'shrink-0 text-muted-foreground transition-transform',
            open && 'rotate-180',
          )}
        />
      </button>
      {open ? <div className="space-y-3 border-t px-4 py-3">{children}</div> : null}
    </div>
  )
}

/** Inline meta chips for stats without MetricPill cards. */
export function SettingsMetaLine({
  items,
}: {
  items: Array<{ label: string; value: string | number }>
}) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5">
      {items.map((item, i) => (
        <span key={item.label} className="inline-flex items-center gap-1">
          {i > 0 ? <span className="text-muted-foreground/50">·</span> : null}
          <span className="tabular-nums text-foreground/90">{item.value}</span>
          <span>{item.label}</span>
        </span>
      ))}
    </span>
  )
}
