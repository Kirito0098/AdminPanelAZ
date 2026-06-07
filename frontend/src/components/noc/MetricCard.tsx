import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  value: ReactNode
  icon: LucideIcon
  accent?: 'cyan' | 'green' | 'amber' | 'red' | 'default'
  sub?: string
}

const accentClasses = {
  cyan: 'text-primary',
  green: 'text-emerald-500',
  amber: 'text-amber-500',
  red: 'text-destructive',
  default: 'text-muted-foreground',
}

export default function MetricCard({ label, value, icon: Icon, accent = 'default', sub }: MetricCardProps) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
          <div className={cn('rounded-md bg-muted p-2', accentClasses[accent])}>
            <Icon size={16} />
          </div>
        </div>
        <div className="mono mt-2 text-2xl font-bold tracking-tight">{value}</div>
        {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  )
}
