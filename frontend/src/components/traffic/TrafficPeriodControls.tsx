import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Calendar, type DateRange } from '@/components/ui/calendar'
import { Button } from '@/components/ui/button'
import {
  availableDateBounds,
  formatLocalDate,
  parseLocalDate,
  validateCustomRange,
} from '@/lib/trafficPeriod'
import { cn } from '@/lib/utils'

/** Widest preset set; overview omits `1h` via default `presets`. */
export type TrafficPeriodPreset = '1h' | '1d' | '7d' | '30d'

export const OVERVIEW_PERIOD_PRESETS: { id: TrafficPeriodPreset; label: string }[] = [
  { id: '1d', label: '1д' },
  { id: '7d', label: '7д' },
  { id: '30d', label: '30д' },
]

/** Chart-only: includes 1h alongside day presets. */
export const CHART_PERIOD_PRESETS: { id: TrafficPeriodPreset; label: string }[] = [
  { id: '1h', label: '1ч' },
  { id: '1d', label: '1д' },
  { id: '7d', label: '7д' },
  { id: '30d', label: '30д' },
]

type Props = {
  retentionDays: number | null
  mode: 'preset' | 'custom'
  preset: TrafficPeriodPreset
  /** Defaults to overview presets (no 1h). Pass `CHART_PERIOD_PRESETS` for the client chart. */
  presets?: { id: TrafficPeriodPreset; label: string }[]
  customFrom?: string // YYYY-MM-DD
  customTo?: string
  showApply?: boolean // true for overview / chart custom Apply
  onPresetChange: (p: TrafficPeriodPreset) => void
  onCustomChange: (from: string, to: string) => void
  onApplyCustom?: () => void
  onNotifyError?: (message: string) => void
  disabled?: boolean
}

const PANEL_WIDTH = 300

function defaultDraftRange(retentionDays: number): { from: string; to: string } {
  const { min, max } = availableDateBounds(retentionDays)
  const from = new Date(max)
  from.setDate(from.getDate() - Math.min(6, retentionDays))
  if (from.getTime() < min.getTime()) {
    return { from: formatLocalDate(min), to: formatLocalDate(max) }
  }
  return { from: formatLocalDate(from), to: formatLocalDate(max) }
}

export default function TrafficPeriodControls({
  retentionDays,
  mode,
  preset,
  presets = OVERVIEW_PERIOD_PRESETS,
  customFrom,
  customTo,
  showApply = false,
  onPresetChange,
  onCustomChange,
  onApplyCustom,
  onNotifyError,
  disabled = false,
}: Props) {
  const customEnabled = retentionDays != null && retentionDays >= 1 && !disabled
  // Popover open state is independent of mode: custom mode can stay active with the
  // calendar closed so the table/chart layout is not pushed aside.
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelPos, setPanelPos] = useState<{ top: number; left: number } | null>(null)

  useEffect(() => {
    if (mode !== 'custom') setOpen(false)
  }, [mode])

  useLayoutEffect(() => {
    if (!open) {
      setPanelPos(null)
      return
    }
    const place = () => {
      const anchor = rootRef.current
      if (!anchor) return
      const rect = anchor.getBoundingClientRect()
      const left = Math.min(
        Math.max(8, rect.right - PANEL_WIDTH),
        window.innerWidth - PANEL_WIDTH - 8,
      )
      const estimatedHeight = 360
      let top = rect.bottom + 6
      if (top + estimatedHeight > window.innerHeight - 8) {
        top = Math.max(8, rect.top - estimatedHeight - 6)
      }
      setPanelPos({ top, left })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
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

  const bounds = useMemo(() => {
    if (retentionDays == null || retentionDays < 1) return null
    return availableDateBounds(retentionDays)
  }, [retentionDays])

  const selected: DateRange = useMemo(() => {
    const from = customFrom ? parseLocalDate(customFrom) ?? undefined : undefined
    const to = customTo ? parseLocalDate(customTo) ?? undefined : undefined
    return { from: from ?? undefined, to: to ?? undefined }
  }, [customFrom, customTo])

  const emitRange = (from: Date, to: Date) => {
    onCustomChange(formatLocalDate(from), formatLocalDate(to))
  }

  const validateAndMaybeApply = (from: Date, to: Date) => {
    if (retentionDays == null) return false
    const err = validateCustomRange(from, to, retentionDays)
    if (err) {
      onNotifyError?.(err)
      return false
    }
    emitRange(from, to)
    return true
  }

  const handlePreset = (p: TrafficPeriodPreset) => {
    setOpen(false)
    onPresetChange(p)
  }

  const handleCustomClick = () => {
    if (!customEnabled || retentionDays == null) return
    if (!customFrom || !customTo) {
      const draft = defaultDraftRange(retentionDays)
      onCustomChange(draft.from, draft.to)
    } else {
      // Signal parent to enter custom mode even when dates already set.
      onCustomChange(customFrom, customTo)
    }
    setOpen((prev) => !prev)
  }

  const handleSelect = (range: DateRange | undefined) => {
    if (!range?.from) {
      onCustomChange('', '')
      return
    }
    if (!range.to) {
      // Partial selection: keep draft start; clear end until second click.
      onCustomChange(formatLocalDate(range.from), '')
      return
    }
    if (!showApply) {
      if (validateAndMaybeApply(range.from, range.to)) setOpen(false)
      return
    }
    emitRange(range.from, range.to)
  }

  const handleApply = () => {
    if (retentionDays == null || !customFrom || !customTo) {
      onNotifyError?.(
        retentionDays == null
          ? 'Срок хранения ещё не загружен.'
          : 'Выберите даты начала и конца периода.',
      )
      return
    }
    const from = parseLocalDate(customFrom)
    const to = parseLocalDate(customTo)
    if (!from || !to) {
      onNotifyError?.('Некорректные даты периода.')
      return
    }
    if (!validateAndMaybeApply(from, to)) return
    onApplyCustom?.()
    setOpen(false)
  }

  const rangeLabel =
    customFrom && customTo
      ? `${customFrom} — ${customTo}`
      : customFrom
        ? `${customFrom} — …`
        : 'Выберите период'

  const panel =
    open && bounds && panelPos
      ? createPortal(
          <div
            ref={panelRef}
            role="dialog"
            aria-label="Свой период"
            className="fixed z-[80] rounded-md border bg-background p-2 shadow-lg"
            style={{ top: panelPos.top, left: panelPos.left, width: PANEL_WIDTH }}
          >
            <Calendar
              mode="range"
              selected={selected}
              onSelect={handleSelect}
              fromDate={bounds.min}
              toDate={bounds.max}
            />
            <div className="mt-2 flex items-center justify-between gap-2 px-1">
              <span className={cn('text-xs text-muted-foreground')}>{rangeLabel}</span>
              {showApply && (
                <Button
                  type="button"
                  size="sm"
                  disabled={disabled || !customFrom || !customTo}
                  onClick={handleApply}
                >
                  Применить
                </Button>
              )}
            </div>
          </div>,
          document.body,
        )
      : null

  return (
    <div ref={rootRef} className="relative flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1">
        {presets.map(({ id, label }) => (
          <Button
            key={id}
            type="button"
            size="sm"
            variant={mode === 'preset' && preset === id ? 'default' : 'outline'}
            disabled={disabled}
            onClick={() => handlePreset(id)}
            className="min-w-[2.5rem]"
          >
            {label}
          </Button>
        ))}
        <Button
          type="button"
          size="sm"
          variant={mode === 'custom' ? 'default' : 'outline'}
          disabled={!customEnabled}
          onClick={handleCustomClick}
          aria-expanded={open}
          aria-haspopup="dialog"
          title={
            retentionDays == null
              ? 'Срок хранения ещё не загружен'
              : 'Свой период'
          }
        >
          Свой
        </Button>
      </div>
      {panel}
    </div>
  )
}
