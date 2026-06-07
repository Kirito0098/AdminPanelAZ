import { cn } from '@/lib/utils'
import { Progress } from './progress'

function IndeterminateBar({ className }: { className?: string }) {
  return (
    <div className={cn('relative h-full w-full overflow-hidden rounded-full bg-secondary', className)}>
      <div className="absolute inset-y-0 w-1/3 animate-[pulse_1.2s_ease-in-out_infinite] bg-primary" />
    </div>
  )
}

export function GlobalProgressBar({ active }: { active: boolean }) {
  if (!active) return null
  return (
    <div className="fixed left-0 right-0 top-0 z-[100] h-1">
      <IndeterminateBar className="h-1 rounded-none" />
    </div>
  )
}

export function InlineProgressBar({ active, label }: { active: boolean; label?: string }) {
  if (!active) return null
  return (
    <div className="mb-4 rounded-md border bg-muted/50 px-4 py-3">
      <div className="mb-2 text-sm text-muted-foreground">{label || 'Выполнение...'}</div>
      <IndeterminateBar className="h-2" />
    </div>
  )
}
