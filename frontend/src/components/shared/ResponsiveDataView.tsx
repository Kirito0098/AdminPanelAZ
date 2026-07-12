import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type ResponsiveBreakpoint = 'md' | 'lg' | 'xl'

const MOBILE_ONLY_CLASS: Record<ResponsiveBreakpoint, string> = {
  md: 'md:hidden',
  lg: 'lg:hidden',
  xl: 'xl:hidden',
}

const DESKTOP_ONLY_CLASS: Record<ResponsiveBreakpoint, string> = {
  md: 'hidden md:block',
  lg: 'hidden lg:block',
  xl: 'hidden xl:block',
}

export interface ResponsiveDataViewProps {
  /** Tailwind breakpoint at which the desktop slot is shown. Defaults to `lg` (1024px). */
  breakpoint?: ResponsiveBreakpoint
  /** Card/list layout shown below the breakpoint. */
  mobile: ReactNode
  /** Table or wide layout shown at/above the breakpoint. */
  desktop: ReactNode
  mobileClassName?: string
  desktopClassName?: string
  className?: string
}

/**
 * Renders separate mobile and desktop data layouts without duplicating breakpoint class names.
 * Uses Tailwind `hidden` / responsive `block` utilities (no runtime matchMedia).
 */
export default function ResponsiveDataView({
  breakpoint = 'lg',
  mobile,
  desktop,
  mobileClassName,
  desktopClassName,
  className,
}: ResponsiveDataViewProps) {
  return (
    <div className={className}>
      <div className={cn(MOBILE_ONLY_CLASS[breakpoint], mobileClassName)}>{mobile}</div>
      <div className={cn(DESKTOP_ONLY_CLASS[breakpoint], desktopClassName)}>{desktop}</div>
    </div>
  )
}
