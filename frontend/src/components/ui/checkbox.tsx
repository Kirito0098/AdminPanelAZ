import * as React from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface CheckboxProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onChange'> {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
}

const Checkbox = React.forwardRef<HTMLButtonElement, CheckboxProps>(
  ({ className, checked = false, disabled, onCheckedChange, onClick, ...props }, ref) => {
    return (
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        disabled={disabled}
        ref={ref}
        onClick={(e) => {
          e.stopPropagation()
          onClick?.(e)
          if (!e.defaultPrevented) {
            onCheckedChange?.(!checked)
          }
        }}
        className={cn(
          'inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-md border-2 transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          'disabled:cursor-not-allowed disabled:opacity-50',
          checked
            ? 'border-primary bg-primary text-primary-foreground'
            : 'border-muted-foreground/50 bg-background hover:border-primary/60',
          className,
        )}
        {...props}
      >
        {checked ? <Check size={12} strokeWidth={3} className="shrink-0" /> : null}
      </button>
    )
  },
)
Checkbox.displayName = 'Checkbox'

export { Checkbox }
