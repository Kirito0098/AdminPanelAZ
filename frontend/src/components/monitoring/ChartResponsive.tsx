import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

type ChartResponsiveProps = {
  /** Pixel height for the chart container (via data-h CSS rules). Omit when parent sets height (e.g. h-full). */
  height?: number
  className?: string
  children: (size: { width: number; height: number }) => ReactNode
}

/** Measures container size for Recharts without inline style attributes (CSP-safe). */
export function ChartResponsive({ height, className, children }: ChartResponsiveProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () =>
      setSize({
        width: Math.max(0, Math.floor(el.clientWidth)),
        height: Math.max(0, Math.floor(el.clientHeight)) || Math.max(0, height ?? 0),
      })
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [height])

  return (
    <div
      ref={ref}
      data-h={height != null ? String(height) : undefined}
      className={cn('chart-responsive w-full', height == null && 'h-full', className)}
    >
      {size.width > 0 && size.height > 0 ? children(size) : null}
    </div>
  )
}
