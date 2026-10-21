import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

type MetricTone = 'default' | 'success' | 'warning' | 'danger'

interface UserMetricProps {
  label: string
  value: ReactNode
  icon?: LucideIcon
  hint?: ReactNode
  /** Слот под значением — например, полоса использования. */
  children?: ReactNode
  tone?: MetricTone
  className?: string
}

const toneValue: Record<MetricTone, string> = {
  default: 'text-foreground',
  success: 'text-emerald-600 dark:text-emerald-400',
  warning: 'text-amber-600 dark:text-amber-400',
  danger: 'text-destructive',
}

/** Компактная метрика для шапки карточки и сводок: подпись, значение, пояснение. */
export default function UserMetric({
  label,
  value,
  icon: Icon,
  hint,
  children,
  tone = 'default',
  className,
}: UserMetricProps) {
  return (
    <div className={cn('rounded-lg border bg-background/70 px-3 py-2.5', className)}>
      <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {Icon && <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />}
        {label}
      </p>
      <p className={cn('mt-1 truncate text-sm font-semibold leading-tight', toneValue[tone])}>
        {value}
      </p>
      {hint && <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{hint}</p>}
      {children && <div className="mt-2">{children}</div>}
    </div>
  )
}
