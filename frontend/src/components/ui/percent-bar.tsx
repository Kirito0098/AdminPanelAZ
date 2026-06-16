import * as React from 'react'
import { cn } from '@/lib/utils'

type PercentBarProps = {
  value: number
  max?: number
  className?: string
  barClassName?: string
  label?: string
}

/** CSP-safe progress fill using SVG geometry (no inline style attributes). */
export const PercentBar = React.forwardRef<HTMLDivElement, PercentBarProps>(function PercentBar(
  { value, max = 100, className, barClassName = 'fill-primary', label },
  ref,
) {
  const percent = max > 0 ? Math.min((value / max) * 100, 100) : 0
  return (
    <div
      ref={ref}
      className={cn('relative overflow-hidden rounded-full bg-secondary', className)}
      role="progressbar"
      aria-valuenow={Math.round(percent)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <svg className="block h-full w-full" viewBox="0 0 100 1" preserveAspectRatio="none" aria-hidden>
        <rect
          x={0}
          y={0}
          width={percent}
          height={1}
          className={cn('transition-all duration-300', barClassName)}
          rx={0.5}
        />
      </svg>
    </div>
  )
})
