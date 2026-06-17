import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface WarperSectionProps {
  title: string
  icon: LucideIcon
  description?: string
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
}

export default function WarperSection({
  title,
  icon: Icon,
  description,
  action,
  children,
  className,
}: WarperSectionProps) {
  return (
    <section className={cn('rounded-lg border bg-card/50 p-4', className)}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Icon className="h-4 w-4" />
            </span>
            {title}
          </h3>
          {description && <p className="mt-1 pl-9 text-xs text-muted-foreground">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

interface WarperStatTileProps {
  label: string
  value: React.ReactNode
  hint?: string
  mono?: boolean
}

export function WarperStatTile({ label, value, hint, mono }: WarperStatTileProps) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 text-sm font-medium', mono && 'font-mono')}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  )
}
