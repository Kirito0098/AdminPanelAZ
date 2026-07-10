import { ChevronRight, Settings } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useLocation } from 'react-router-dom'
import type { SettingsNavItem } from '@/components/settings/SettingsNav'
import { getVisibleNavGroups } from '@/components/settings/SettingsNav'
import { cn } from '@/lib/utils'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'

const HOVER_CLOSE_DELAY_MS = 120
const PANEL_WIDTH = 288
const VIEWPORT_MARGIN = 8

type FlyoutPos = {
  top: number
  left: number
  maxHeight?: number
}

function SettingsSubGroupHeader({ label }: { label: string }) {
  return <p className="px-2.5 pb-1 pt-3 text-xs font-medium text-muted-foreground first:pt-1">{label}</p>
}

function SettingsFlyoutLink({
  item,
  onNavigate,
}: {
  item: SettingsNavItem
  onNavigate?: () => void
}) {
  const Icon = item.icon

  return (
    <NavLink
      to={`/settings/${item.id}`}
      end
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 rounded-xl px-2.5 py-2 text-sm font-medium transition-colors',
          isActive
            ? 'bg-primary/10 text-foreground ring-1 ring-primary/20'
            : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cn(
              'absolute bottom-2 left-0 top-2 w-0.5 rounded-full',
              isActive ? 'bg-primary' : 'opacity-0',
            )}
            aria-hidden
          />
          <span
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-colors',
              isActive
                ? 'border-primary/25 bg-primary/15 text-primary'
                : 'border-transparent bg-muted/60 text-muted-foreground group-hover:bg-muted group-hover:text-foreground',
            )}
          >
            <Icon size={17} strokeWidth={2} />
          </span>
          <span className="min-w-0 truncate leading-snug">{item.label}</span>
        </>
      )}
    </NavLink>
  )
}

export default function SettingsSidebarSection({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth()
  const { isSettingsTabEnabled, isEnabled } = useFeatureModules()
  const location = useLocation()
  const isAdmin = user?.role === 'admin'
  const isSettingsActive = location.pathname.startsWith('/settings')

  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const closeTimerRef = useRef<number | null>(null)
  const [pinnedOpen, setPinnedOpen] = useState(false)
  const [hovering, setHovering] = useState(false)
  const [flyoutPos, setFlyoutPos] = useState<FlyoutPos>({ top: 0, left: 0 })

  const visibleGroups = useMemo(
    () => getVisibleNavGroups(isAdmin, isSettingsTabEnabled, isEnabled),
    [isAdmin, isSettingsTabEnabled, isEnabled],
  )
  const visibleItemsKey = useMemo(
    () => visibleGroups.flatMap((group) => group.items.map((item) => item.id)).join(','),
    [visibleGroups],
  )
  const expanded = pinnedOpen || hovering

  const updateFlyoutPosition = useCallback(() => {
    const trigger = triggerRef.current
    const panel = panelRef.current
    if (!trigger) return

    const rect = trigger.getBoundingClientRect()
    let left = rect.right + VIEWPORT_MARGIN
    if (left + PANEL_WIDTH > window.innerWidth - VIEWPORT_MARGIN) {
      left = rect.left - PANEL_WIDTH - VIEWPORT_MARGIN
    }

    const viewportMax = window.innerHeight - VIEWPORT_MARGIN * 2
    const panelHeight = panel?.scrollHeight ?? 0

    let top = rect.top
    let maxHeight: number | undefined

    if (panelHeight > viewportMax) {
      top = VIEWPORT_MARGIN
      maxHeight = viewportMax
    } else if (panelHeight > 0) {
      if (top + panelHeight > window.innerHeight - VIEWPORT_MARGIN) {
        top = window.innerHeight - VIEWPORT_MARGIN - panelHeight
      }
      top = Math.max(VIEWPORT_MARGIN, top)
    } else {
      top = Math.max(VIEWPORT_MARGIN, rect.top)
    }

    setFlyoutPos((prev) => {
      if (prev.top === top && prev.left === left && prev.maxHeight === maxHeight) return prev
      return { top, left, maxHeight }
    })
  }, [])

  const handleTriggerClick = () => {
    setPinnedOpen((open) => {
      const next = !open
      if (!next) {
        setHovering(false)
        if (closeTimerRef.current !== null) {
          window.clearTimeout(closeTimerRef.current)
          closeTimerRef.current = null
        }
      }
      return next
    })
  }

  const openHover = () => {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current)
      closeTimerRef.current = null
    }
    setHovering(true)
  }

  const scheduleCloseHover = () => {
    if (pinnedOpen) return
    closeTimerRef.current = window.setTimeout(() => {
      setHovering(false)
      closeTimerRef.current = null
    }, HOVER_CLOSE_DELAY_MS)
  }

  useLayoutEffect(() => {
    if (!expanded) return
    updateFlyoutPosition()
    panelRef.current?.scrollTo({ top: 0 })
  }, [expanded, visibleItemsKey, updateFlyoutPosition])

  useEffect(() => {
    if (!expanded) return
    const onLayoutChange = () => updateFlyoutPosition()
    window.addEventListener('resize', onLayoutChange)
    window.addEventListener('scroll', onLayoutChange, true)
    return () => {
      window.removeEventListener('resize', onLayoutChange)
      window.removeEventListener('scroll', onLayoutChange, true)
    }
  }, [expanded, updateFlyoutPosition])

  useEffect(() => {
    if (!pinnedOpen) return
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node
      if (triggerRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      setPinnedOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [pinnedOpen])

  useEffect(() => {
    return () => {
      if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current)
    }
  }, [])

  if (visibleGroups.length === 0) return null

  const flyoutPanel = expanded
    ? createPortal(
        <div
          ref={panelRef}
          id="settings-flyout-panel"
          className={cn(
            'fixed z-[60] w-72 origin-left rounded-xl border border-border/80 bg-card p-2 shadow-lg',
            'animate-in fade-in-0 zoom-in-95 slide-in-from-left-2 duration-150',
            flyoutPos.maxHeight != null && 'overflow-y-auto',
          )}
          style={{
            top: flyoutPos.top,
            left: flyoutPos.left,
            ...(flyoutPos.maxHeight != null ? { maxHeight: flyoutPos.maxHeight } : {}),
          }}
          onMouseEnter={openHover}
          onMouseLeave={scheduleCloseHover}
        >
          <div className="border-b border-border/60 px-2.5 py-2">
            <p className="text-sm font-medium leading-snug text-foreground">Настройки</p>
            <p className="text-xs leading-relaxed text-muted-foreground">Панель и профиль</p>
          </div>
          <div className="px-0.5 pt-0.5">
            {visibleGroups.map((group) => (
              <div key={group.label}>
                {visibleGroups.length > 1 && <SettingsSubGroupHeader label={group.label} />}
                <ul className="space-y-0.5 pb-1">
                  {group.items.map((item) => (
                    <li key={item.id}>
                      <SettingsFlyoutLink item={item} onNavigate={onNavigate} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>,
        document.body,
      )
    : null

  return (
    <li className="list-none">
      <button
        ref={triggerRef}
        type="button"
        onClick={handleTriggerClick}
        onMouseEnter={openHover}
        onMouseLeave={scheduleCloseHover}
        aria-expanded={expanded}
        aria-controls="settings-flyout-panel"
        className={cn(
          'group relative flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-sm font-medium transition-colors',
          isSettingsActive || expanded
            ? 'bg-primary/10 text-foreground ring-1 ring-primary/20'
            : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
        )}
      >
        <span
          className={cn(
            'absolute bottom-2 left-0 top-2 w-0.5 rounded-full',
            isSettingsActive ? 'bg-primary' : 'opacity-0',
          )}
          aria-hidden
        />
        <span
          className={cn(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-colors',
            isSettingsActive
              ? 'border-primary/25 bg-primary/15 text-primary'
              : 'border-transparent bg-muted/60 text-muted-foreground group-hover:bg-muted group-hover:text-foreground',
          )}
        >
          <Settings size={17} strokeWidth={2} />
        </span>
        <span className="min-w-0 flex-1 truncate text-left leading-snug">Настройки</span>
        <ChevronRight
          size={16}
          className={cn(
            'shrink-0 text-muted-foreground transition-transform duration-200',
            expanded && 'translate-x-0.5 text-foreground',
          )}
          aria-hidden
        />
      </button>
      {flyoutPanel}
    </li>
  )
}
