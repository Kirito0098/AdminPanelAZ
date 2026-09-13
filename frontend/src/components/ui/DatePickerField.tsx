import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  autoUpdate,
  computePosition,
  flip,
  offset,
  shift,
  size,
} from '@floating-ui/dom'
import { Calendar as CalendarIcon } from 'lucide-react'
import { Calendar } from '@/components/ui/calendar'
import { Button } from '@/components/ui/button'
import { formatLocalDate, parseLocalDate } from '@/lib/trafficPeriod'
import { cn } from '@/lib/utils'

const VIEWPORT_PADDING = 8

function formatDisplayDate(iso: string): string {
  const parsed = parseLocalDate(iso)
  if (!parsed) return ''
  const dd = String(parsed.getDate()).padStart(2, '0')
  const mm = String(parsed.getMonth() + 1).padStart(2, '0')
  return `${dd}.${mm}.${parsed.getFullYear()}`
}

export type DatePickerFieldProps = {
  id?: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  className?: string
  placeholder?: string
  /** Allow clearing the value from the calendar footer. */
  allowClear?: boolean
  fromDate?: Date
}

/** Themed single-date picker (YYYY-MM-DD value) — avoids native light OS calendars. */
export default function DatePickerField({
  id,
  value,
  onChange,
  disabled = false,
  className,
  placeholder = 'ДД.ММ.ГГГГ',
  allowClear = true,
  fromDate,
}: DatePickerFieldProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelPos, setPanelPos] = useState<{ top: number; left: number } | null>(null)

  const selected = useMemo(() => (value ? parseLocalDate(value) ?? undefined : undefined), [value])

  useLayoutEffect(() => {
    if (!open) {
      setPanelPos(null)
      return
    }

    const anchor = rootRef.current
    const panel = panelRef.current
    if (!anchor || !panel) return

    const update = () => {
      void computePosition(anchor, panel, {
        strategy: 'fixed',
        placement: 'bottom-start',
        middleware: [
          offset(6),
          // Prefer below; flip above only when there is not enough space.
          flip({
            fallbackPlacements: ['top-start', 'bottom-end', 'top-end'],
            padding: VIEWPORT_PADDING,
          }),
          shift({ padding: VIEWPORT_PADDING }),
          size({
            padding: VIEWPORT_PADDING,
            apply({ availableWidth, availableHeight, elements }) {
              Object.assign(elements.floating.style, {
                maxWidth: `${Math.max(0, availableWidth)}px`,
                maxHeight: `${Math.max(0, availableHeight)}px`,
              })
            },
          }),
        ],
      }).then(({ x, y }) => {
        setPanelPos({ top: y, left: x })
      })
    }

    const cleanup = autoUpdate(anchor, panel, update, {
      ancestorScroll: true,
      ancestorResize: true,
      elementResize: true,
    })
    return cleanup
  }, [open])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node | null
      if (!target) return
      if (rootRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('touchstart', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('touchstart', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const display = value ? formatDisplayDate(value) : ''

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <button
        id={id}
        type="button"
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => !disabled && setOpen((prev) => !prev)}
        className={cn(
          'flex h-10 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-left text-sm ring-offset-background',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          'disabled:cursor-not-allowed disabled:opacity-50',
          'lg:h-11 lg:text-base xl:h-12',
          !display && 'text-muted-foreground',
        )}
      >
        <span className="min-w-0 truncate">{display || placeholder}</span>
        <CalendarIcon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      </button>

      {open &&
        createPortal(
          <div
            ref={panelRef}
            data-datepicker-portal=""
            role="dialog"
            aria-label="Выбор даты"
            // Radix modal Dialog sets pointer-events:none on body; re-enable for this portal.
            className="pointer-events-auto fixed z-[80] w-[300px] overflow-auto rounded-xl border bg-popover p-2 text-popover-foreground shadow-xl"
            style={{
              top: panelPos?.top ?? 0,
              left: panelPos?.left ?? 0,
              visibility: panelPos ? 'visible' : 'hidden',
            }}
          >
            <Calendar
              mode="single"
              selected={selected}
              fromDate={fromDate}
              onSelect={(date) => {
                if (!date) return
                onChange(formatLocalDate(date))
                setOpen(false)
              }}
            />
            <div className="mt-1 flex items-center justify-between gap-2 border-t px-1 pt-2">
              {allowClear ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 px-2 text-xs"
                  onClick={() => {
                    onChange('')
                    setOpen(false)
                  }}
                >
                  Очистить
                </Button>
              ) : (
                <span />
              )}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 px-2 text-xs"
                onClick={() => {
                  onChange(formatLocalDate(new Date()))
                  setOpen(false)
                }}
              >
                Сегодня
              </Button>
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}
