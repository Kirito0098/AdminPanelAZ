import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface PageSectionHeaderProps {
  icon: LucideIcon
  title: ReactNode
  description?: ReactNode
  /** Badges or extra content rendered beside the title. */
  titleAddon?: ReactNode
  /** Toolbar controls; wraps below the title on narrow screens. */
  actions?: ReactNode
  className?: string
  iconClassName?: string
}

/**
 * Standard page hero: icon, title block, and a flex-wrapping action toolbar.
 * Uses column layout on mobile and row layout from the `sm` breakpoint.
 */
export default function PageSectionHeader({
  icon: Icon,
  title,
  description,
  titleAddon,
  actions,
  className,
  iconClassName,
}: PageSectionHeaderProps) {
  return (
    <div className={cn('flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between', className)}>
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary',
            iconClassName,
          )}
        >
          <Icon size={22} />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-bold tracking-tight">{title}</h2>
            {titleAddon}
          </div>
          {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
        </div>
      </div>
      {actions ? (
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
          {actions}
        </div>
      ) : null}
    </div>
  )
}
