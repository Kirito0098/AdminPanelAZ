import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ChevronDown, Info } from 'lucide-react'
import DocsLink from '@/components/shared/DocsLink'
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
  /** Omit when the section header already carries the title. */
  title?: string
  count?: number | string
  meta?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  const hasHeading = Boolean(title) || (count != null && count !== '')
  return (
    <div
      className={cn(
        'flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between',
        className,
      )}
    >
      <div className="min-w-0">
        {hasHeading ? (
          <div className="flex flex-wrap items-center gap-2">
            {title ? <h3 className="text-sm font-semibold tracking-tight">{title}</h3> : null}
            {count != null && count !== '' ? (
              <Badge variant="secondary" className="tabular-nums">
                {count}
              </Badge>
            ) : null}
          </div>
        ) : null}
        {meta ? (
          <div className={cn('text-xs text-muted-foreground', hasHeading && 'mt-1')}>{meta}</div>
        ) : null}
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
  tone = 'default',
}: {
  children: ReactNode
  className?: string
  padded?: boolean
  /** `danger` tints the panel for irreversible actions. */
  tone?: 'default' | 'danger'
}) {
  return (
    <div
      className={cn(
        'rounded-xl border border-border/80 bg-card shadow-sm',
        tone === 'danger' && 'border-destructive/30 bg-destructive/[0.04]',
        className,
      )}
    >
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
    <div className={cn('rounded-xl border border-border/80 bg-muted/20', className)}>
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left transition-colors hover:bg-muted/40"
        aria-expanded={open}
      >
        <div className="flex min-w-0 items-start gap-2.5">
          {icon ? (
            <span className="mt-0.5 shrink-0 rounded-lg bg-muted/60 p-1.5 text-muted-foreground">
              {icon}
            </span>
          ) : null}
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
      {open ? <div className="space-y-3 border-t border-border/70 px-4 py-3">{children}</div> : null}
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

/** Section hero for a single settings section — icon, title, hint and trailing actions. */
export function SettingsSectionHeader({
  icon: Icon,
  title,
  description,
  hint,
  docsHref,
  badge,
  actions,
  className,
}: {
  icon: LucideIcon
  title: string
  description?: string
  hint?: string
  docsHref?: string
  badge?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  const hasTrailing = Boolean(docsHref || actions)
  return (
    <section
      className={cn(
        'rounded-xl border border-border/80 bg-gradient-to-br from-primary/[0.06] via-card to-card p-4',
        className,
      )}
    >
      <div
        className={cn(
          'flex flex-col gap-3',
          hasTrailing && 'sm:flex-row sm:items-start sm:justify-between',
        )}
      >
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/15">
            <Icon size={18} aria-hidden />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
              {badge ? <span className="inline-flex items-center">{badge}</span> : null}
            </div>
            {description ? (
              <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
            ) : null}
            {hint ? (
              <p className="mt-1 flex items-start gap-1 text-[11px] text-muted-foreground/80">
                <Info size={12} className="mt-0.5 shrink-0 text-amber-500/80" aria-hidden />
                <span>{hint}</span>
              </p>
            ) : null}
          </div>
        </div>
        {hasTrailing ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {docsHref ? <DocsLink href={docsHref} variant="button" /> : null}
            {actions}
          </div>
        ) : null}
      </div>
    </section>
  )
}

/** Small labelled metric card with optional progress bar. */
export function SettingsStatCard({
  label,
  value,
  hint,
  progress,
  icon: Icon,
  className,
}: {
  label: string
  value: ReactNode
  hint?: string
  progress?: number
  icon?: LucideIcon
  className?: string
}) {
  const pct = progress == null ? null : Math.min(100, Math.max(0, progress))
  return (
    <div className={cn('rounded-xl border border-border/80 bg-card p-4', className)}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        {Icon ? <Icon size={14} className="shrink-0 text-muted-foreground/70" aria-hidden /> : null}
      </div>
      <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}
      {pct != null ? (
        <div
          className="mt-2 h-1 w-full overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={Math.round(pct)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
        </div>
      ) : null}
    </div>
  )
}

/** Destructive-actions block — tinted card with title, description and trailing controls. */
export function SettingsDangerZone({
  title,
  description,
  children,
  className,
}: {
  title: string
  description?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'rounded-xl border border-destructive/30 bg-destructive/[0.04] p-4',
        className,
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          {description ? (
            <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">{children}</div>
      </div>
    </div>
  )
}
