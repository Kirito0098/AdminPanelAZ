import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  value: ReactNode
  icon: LucideIcon
  accent?: 'cyan' | 'green' | 'amber' | 'red' | 'default'
  sub?: string
}

const accentStyles = {
  cyan: 'bg-primary/15 text-primary',
  green: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  amber: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  red: 'bg-destructive/15 text-destructive',
  default: 'bg-muted text-muted-foreground',
} as const

export default function MetricCard({ label, value, icon: Icon, accent = 'default', sub }: MetricCardProps) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card/80 p-3 shadow-sm">
      <div className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl', accentStyles[accent])}>
        <Icon size={18} strokeWidth={2} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mono truncate text-lg font-semibold leading-tight">{value}</p>
        {sub && <p className="mt-0.5 truncate text-xs text-muted-foreground">{sub}</p>}
      </div>
    </div>
  )
}
