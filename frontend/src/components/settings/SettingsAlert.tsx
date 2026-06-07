import type { LucideIcon } from 'lucide-react'
import { AlertTriangle, Info } from 'lucide-react'
import { cn } from '@/lib/utils'

type AlertVariant = 'warning' | 'danger' | 'info'

const variantStyles: Record<AlertVariant, { box: string; icon: LucideIcon }> = {
  warning: {
    box: 'border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-100',
    icon: AlertTriangle,
  },
  danger: {
    box: 'border-destructive/40 bg-destructive/10 text-destructive',
    icon: AlertTriangle,
  },
  info: {
    box: 'border-primary/30 bg-primary/5 text-foreground',
    icon: Info,
  },
}

interface SettingsAlertProps {
  variant: AlertVariant
  title?: string
  children: React.ReactNode
  className?: string
}

export default function SettingsAlert({ variant, title, children, className }: SettingsAlertProps) {
  const { box, icon: Icon } = variantStyles[variant]
  return (
    <div className={cn('flex gap-3 rounded-lg border p-4 text-sm', box, className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 space-y-1">
        {title && <p className="font-medium">{title}</p>}
        <div className="text-muted-foreground [&_strong]:text-foreground">{children}</div>
      </div>
    </div>
  )
}
