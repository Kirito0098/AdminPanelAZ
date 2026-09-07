import { useEffect, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type ResponsiveBreakpoint = 'md' | 'lg' | 'xl'

/** Tailwind default min-widths for `md` / `lg` / `xl`. */
const MIN_WIDTH_PX: Record<ResponsiveBreakpoint, number> = {
  md: 768,
  lg: 1024,
  xl: 1280,
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

function useMinWidth(breakpoint: ResponsiveBreakpoint): boolean {
  const query = `(min-width: ${MIN_WIDTH_PX[breakpoint]}px)`
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches,
  )

  useEffect(() => {
    const mediaQuery = window.matchMedia(query)
    const onChange = () => setMatches(mediaQuery.matches)
    onChange()
    mediaQuery.addEventListener('change', onChange)
    return () => mediaQuery.removeEventListener('change', onChange)
  }, [query])

  return matches
}

/**
 * Renders either the mobile or desktop data layout for the active breakpoint.
 * Only one tree is mounted so effects (e.g. ProxyNodePanel status fetch) do not
 * run twice via CSS-only dual DOM.
 */
export default function ResponsiveDataView({
  breakpoint = 'lg',
  mobile,
  desktop,
  mobileClassName,
  desktopClassName,
  className,
}: ResponsiveDataViewProps) {
  const isDesktop = useMinWidth(breakpoint)

  return (
    <div className={className}>
      {isDesktop ? (
        <div className={cn(desktopClassName)}>{desktop}</div>
      ) : (
        <div className={cn(mobileClassName)}>{mobile}</div>
      )}
    </div>
  )
}
