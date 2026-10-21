import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

export type ViewModeOption<T extends string> = {
  value: T
  label: string
  icon?: LucideIcon
  title?: string
}

type ViewModeToggleProps<T extends string> = {
  value: T
  onChange: (value: T) => void
  options: readonly ViewModeOption<T>[]
  ariaLabel: string
  className?: string
}

/** Compact segmented control for switching how a data list is grouped. */
export default function ViewModeToggle<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  className,
}: ViewModeToggleProps<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        'inline-flex h-9 shrink-0 items-center rounded-lg border bg-muted/40 p-0.5',
        className,
      )}
    >
      {options.map((option) => {
        const active = value === option.value
        const Icon = option.icon
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            title={option.title ?? option.label}
            onClick={() => onChange(option.value)}
            className={cn(
              'inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors',
              active
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {Icon ? <Icon size={14} /> : null}
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
