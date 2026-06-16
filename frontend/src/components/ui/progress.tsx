import * as React from 'react'
import { cn } from '@/lib/utils'
import { PercentBar } from '@/components/ui/percent-bar'

const Progress = React.forwardRef<
  HTMLDivElement,
  React.ComponentPropsWithoutRef<typeof PercentBar>
>(({ className, value, ...props }, ref) => (
  <PercentBar ref={ref} value={value ?? 0} className={cn('h-4 w-full', className)} {...props} />
))
Progress.displayName = 'Progress'

export { Progress }
