import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

type SectionTone = 'default' | 'warning' | 'danger'

interface UserSectionProps {
  icon?: LucideIcon
  title: string
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  tone?: SectionTone
  className?: string
  contentClassName?: string
}

const toneCard: Record<SectionTone, string> = {
  default: '',
  warning: 'border-amber-500/40',
  danger: 'border-destructive/40',
}

const toneIcon: Record<SectionTone, string> = {
  default: 'bg-primary/10 text-primary',
  warning: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  danger: 'bg-destructive/10 text-destructive',
}

/**
 * Единая секция карточки абонента: иконка, заголовок, пояснение и действия справа.
 * Используется на всех вкладках, чтобы блоки выглядели одинаково.
 */
export default function UserSection({
  icon: Icon,
  title,
  description,
  actions,
  children,
  tone = 'default',
  className,
  contentClassName,
}: UserSectionProps) {
  return (
    <section
      className={cn(
        'overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm',
        toneCard[tone],
        className,
      )}
    >
      <header className="flex flex-col gap-3 border-b bg-muted/20 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div className="flex min-w-0 items-start gap-3">
          {Icon && (
            <span
              className={cn(
                'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                toneIcon[tone],
              )}
            >
              <Icon className="h-4 w-4" aria-hidden />
            </span>
          )}
          <div className="min-w-0">
            <h3 className="text-sm font-semibold leading-tight">{title}</h3>
            {description && (
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
            )}
          </div>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2 sm:shrink-0">{actions}</div>}
      </header>
      <div className={cn('px-4 py-4 sm:px-5', contentClassName)}>{children}</div>
    </section>
  )
}
