import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { metricBarClass } from '@/lib/metricColors'
import { cn } from '@/lib/utils'

export function healthBadgeVariant(level?: string): 'success' | 'warning' | 'destructive' | 'outline' {
  if (level === 'critical') return 'destructive'
  if (level === 'warn') return 'warning'
  if (level === 'ok') return 'success'
  return 'outline'
}

export function formatMetricPercent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

/** Compact CPU/RAM: bar + readable percent beside it. */
export function ResourceMetricInline({
  value,
  label,
  className,
  barClassName = 'w-14',
}: {
  value?: number | null
  label: string
  className?: string
  /** Tailwind width class for the progress track (default w-14). */
  barClassName?: string
}) {
  if (value == null || Number.isNaN(value)) {
    return <span className="text-xs text-muted-foreground">н/д</span>
  }
  const clamped = Math.min(100, Math.max(0, value))
  return (
    <div className={cn('flex min-w-0 items-center gap-2', className)}>
      <Progress
        value={clamped}
        barClassName={metricBarClass(value)}
        className={cn('h-1.5 min-w-0 shrink', barClassName)}
        label={label}
      />
      <span className="shrink-0 text-xs tabular-nums text-foreground/90">{formatMetricPercent(value)}</span>
    </div>
  )
}

export function HealthScoreBadge({
  score,
  level,
  className,
}: {
  score?: number | null
  level?: string
  className?: string
}) {
  if (score == null) {
    return <span className="text-xs text-muted-foreground">—</span>
  }
  return (
    <Badge
      variant={healthBadgeVariant(level)}
      className={cn('h-5 min-w-[2.25rem] justify-center px-1.5 font-mono text-[11px] tabular-nums', className)}
      title={level ? `Health: ${score} (${level})` : `Health: ${score}`}
    >
      {score}
    </Badge>
  )
}
