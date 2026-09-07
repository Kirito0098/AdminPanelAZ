import { useEffect, useRef } from 'react'

/** True when the document is in a background tab (safe for SSR). */
export function isDocumentHidden(): boolean {
  return typeof document !== 'undefined' && document.hidden
}

type Options = {
  enabled?: boolean
  /** Fire `tick` once when the effect mounts (if the tab is visible). */
  runOnMount?: boolean
  /** Called when the tab becomes visible again (not on mount). */
  onBecomeVisible?: () => void
  /** When this value changes, restart the interval (e.g. pending id). */
  restartKey?: string | number | boolean | null
}

/**
 * Run `tick` on an interval while the document is visible.
 * Skips ticks when the tab is hidden; optionally refreshes when it becomes visible.
 */
export function useIntervalWhenVisible(
  tick: () => void,
  intervalMs: number,
  options: Options = {},
): void {
  const { enabled = true, runOnMount = false, onBecomeVisible, restartKey = null } = options
  const tickRef = useRef(tick)
  const onVisibleRef = useRef(onBecomeVisible)
  tickRef.current = tick
  onVisibleRef.current = onBecomeVisible

  useEffect(() => {
    if (!enabled) return

    if (runOnMount && !isDocumentHidden()) {
      tickRef.current()
    }

    const id = window.setInterval(() => {
      if (isDocumentHidden()) return
      tickRef.current()
    }, intervalMs)

    const onVisibility = () => {
      if (isDocumentHidden()) return
      onVisibleRef.current?.()
    }
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [enabled, intervalMs, runOnMount, restartKey])
}
