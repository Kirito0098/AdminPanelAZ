import { useEffect, useMemo, useState } from 'react'
import { Calendar, type DateRange } from '@/components/ui/calendar'
import { Button } from '@/components/ui/button'
import {
  availableDateBounds,
  formatLocalDate,
  parseLocalDate,
  validateCustomRange,
} from '@/lib/trafficPeriod'
import { cn } from '@/lib/utils'

type Preset = '1d' | '7d' | '30d'

type Props = {
  retentionDays: number | null
  mode: 'preset' | 'custom'
  preset: Preset
  customFrom?: string // YYYY-MM-DD
  customTo?: string
  showApply?: boolean // true for overview
  onPresetChange: (p: Preset) => void
  onCustomChange: (from: string, to: string) => void
  onApplyCustom?: () => void
  onNotifyError?: (message: string) => void
  disabled?: boolean
}

const PRESETS: { id: Preset; label: string }[] = [
  { id: '1d', label: '1д' },
  { id: '7d', label: '7д' },
  { id: '30d', label: '30д' },
]

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
  const [open, setOpen] = useState(mode === 'custom')

  useEffect(() => {
    setOpen(mode === 'custom')
  }, [mode])

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

  const handlePreset = (p: Preset) => {
    setOpen(false)
    onPresetChange(p)
  }

  const handleCustomClick = () => {
    if (!customEnabled || retentionDays == null) return
    setOpen(true)
    if (!customFrom || !customTo) {
      const draft = defaultDraftRange(retentionDays)
      onCustomChange(draft.from, draft.to)
    } else {
      // Signal parent to enter custom mode even when dates already set.
      onCustomChange(customFrom, customTo)
    }
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
      validateAndMaybeApply(range.from, range.to)
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
  }

  const rangeLabel =
    customFrom && customTo
      ? `${customFrom} — ${customTo}`
      : customFrom
        ? `${customFrom} — …`
        : 'Выберите период'

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1">
        {PRESETS.map(({ id, label }) => (
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
          title={
            retentionDays == null
              ? 'Срок хранения ещё не загружен'
              : 'Свой период'
          }
        >
          Свой
        </Button>
      </div>

      {mode === 'custom' && open && bounds && (
        <div className="rounded-md border bg-background p-2 shadow-sm">
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
        </div>
      )}
    </div>
  )
}
