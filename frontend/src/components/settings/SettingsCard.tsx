import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Card primitives for the settings hub — same API as `ui/card`, denser spacing
 * and softer corners to match the hub-dashboard layout.
 */
const SettingsCard = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'rounded-xl border border-border/80 bg-card text-card-foreground shadow-sm',
        className,
      )}
      {...props}
    />
  ),
)
SettingsCard.displayName = 'SettingsCard'

const SettingsCardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex flex-col gap-1 p-4 sm:p-5', className)} {...props} />
  ),
)
SettingsCardHeader.displayName = 'SettingsCardHeader'

const SettingsCardTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn('text-sm font-semibold leading-tight tracking-tight', className)}
    {...props}
  />
))
SettingsCardTitle.displayName = 'SettingsCardTitle'

const SettingsCardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn('text-xs leading-relaxed text-muted-foreground', className)}
    {...props}
  />
))
SettingsCardDescription.displayName = 'SettingsCardDescription'

const SettingsCardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('p-4 pt-0 sm:p-5 sm:pt-0', className)} {...props} />
  ),
)
SettingsCardContent.displayName = 'SettingsCardContent'

const SettingsCardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('flex items-center p-4 pt-0 sm:p-5 sm:pt-0', className)}
      {...props}
    />
  ),
)
SettingsCardFooter.displayName = 'SettingsCardFooter'

export {
  SettingsCard,
  SettingsCardHeader,
  SettingsCardTitle,
  SettingsCardDescription,
  SettingsCardContent,
  SettingsCardFooter,
}
