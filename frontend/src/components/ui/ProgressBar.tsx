import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Progress } from './progress'

function IndeterminateBar({ className, size = 'md' }: { className?: string; size?: 'sm' | 'md' }) {
  return (
    <div
      className={cn(
        'relative w-full overflow-hidden rounded-full bg-secondary',
        size === 'sm' ? 'h-1' : 'h-2',
        className,
      )}
    >
      <div className="absolute inset-y-0 w-1/3 animate-progress-indeterminate rounded-full bg-primary" />
    </div>
  )
}

export interface AppProgressProps {
  /** null or undefined = indeterminate */
  value?: number | null
  label?: string
  showPercent?: boolean
  className?: string
  size?: 'sm' | 'md'
  icon?: boolean
}

export function AppProgress({
  value,
  label,
  showPercent = true,
  className,
  size = 'md',
  icon = false,
}: AppProgressProps) {
  const isDeterminate = value != null && value >= 0
  const clampedValue = isDeterminate ? Math.min(100, Math.max(0, value)) : undefined

  return (
    <div
      className={cn(
        'rounded-lg border border-primary/20 bg-primary/5 px-4 py-3',
        className,
      )}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clampedValue}
      aria-label={label || 'Выполнение...'}
    >
      {(label || icon) && (
        <div className="mb-2 flex items-center gap-2 text-sm">
          {icon && <Loader2 size={14} className="animate-spin text-primary" />}
          {label && <span className="font-medium text-foreground">{label}</span>}
          {isDeterminate && showPercent && (
            <span className="ml-auto tabular-nums text-muted-foreground">{clampedValue}%</span>
          )}
        </div>
      )}
      {isDeterminate ? (
        <div className="flex items-center gap-3">
          <Progress value={clampedValue} className={cn('flex-1', size === 'sm' && 'h-1.5')} />
          {!label && showPercent && (
            <span className="shrink-0 text-sm font-medium tabular-nums text-muted-foreground">
              {clampedValue}%
            </span>
          )}
        </div>
      ) : (
        <IndeterminateBar size={size} />
      )}
    </div>
  )
}

export function GlobalProgressBar({ active }: { active: boolean }) {
  if (!active) return null
  return (
    <div className="fixed left-0 right-0 top-0 z-[100] h-1 overflow-hidden bg-secondary">
      <div className="absolute inset-y-0 w-1/3 animate-progress-indeterminate bg-primary" />
    </div>
  )
}

export interface InlineProgressBarProps {
  active: boolean
  label?: string
  value?: number | null
}

export function InlineProgressBar({ active, label, value }: InlineProgressBarProps) {
  if (!active) return null
  return (
    <AppProgress
      value={value}
      label={label || 'Выполнение...'}
      showPercent={value != null}
      icon
      className="mb-4"
    />
  )
}
