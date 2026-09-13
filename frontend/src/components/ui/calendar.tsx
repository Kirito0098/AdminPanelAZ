import * as React from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type DateRange = { from?: Date; to?: Date }

type CalendarBaseProps = {
  disabled?: (date: Date) => boolean
  fromDate?: Date
  toDate?: Date
  className?: string
}

export type CalendarProps =
  | (CalendarBaseProps & {
      mode: 'range'
      selected?: DateRange
      onSelect?: (range: DateRange | undefined) => void
    })
  | (CalendarBaseProps & {
      mode: 'single'
      selected?: Date
      onSelect?: (date: Date | undefined) => void
    })

const WEEKDAYS = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'] as const

function startOfLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

function formatLocalDayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

function monthLabel(d: Date): string {
  const raw = d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
  return raw.charAt(0).toUpperCase() + raw.slice(1)
}

/** Monday-first grid cells for the visible month (includes leading/trailing padding days). */
function buildMonthCells(view: Date): Date[] {
  const first = new Date(view.getFullYear(), view.getMonth(), 1)
  const mondayOffset = (first.getDay() + 6) % 7
  const gridStart = new Date(first)
  gridStart.setDate(first.getDate() - mondayOffset)
  const cells: Date[] = []
  for (let i = 0; i < 42; i++) {
    const cell = new Date(gridStart)
    cell.setDate(gridStart.getDate() + i)
    cells.push(cell)
  }
  return cells
}

function isOutsideBounds(day: Date, fromDate?: Date, toDate?: Date): boolean {
  const t = startOfLocalDay(day).getTime()
  if (fromDate && t < startOfLocalDay(fromDate).getTime()) return true
  if (toDate && t > startOfLocalDay(toDate).getTime()) return true
  return false
}

function isInSelectedRange(day: Date, selected?: DateRange): boolean {
  if (!selected?.from || !selected?.to) return false
  const t = startOfLocalDay(day).getTime()
  const a = startOfLocalDay(selected.from).getTime()
  const b = startOfLocalDay(selected.to).getTime()
  return t >= Math.min(a, b) && t <= Math.max(a, b)
}

export function Calendar(props: CalendarProps) {
  const { disabled, fromDate, toDate, className, mode } = props
  const initial =
    mode === 'single'
      ? (props.selected ?? toDate ?? new Date())
      : (props.selected?.to ?? props.selected?.from ?? toDate ?? new Date())
  const [view, setView] = React.useState(
    () => new Date(initial.getFullYear(), initial.getMonth(), 1),
  )

  const selectedKey =
    mode === 'single'
      ? props.selected
        ? formatLocalDayKey(props.selected)
        : ''
      : `${props.selected?.from ? formatLocalDayKey(props.selected.from) : ''}|${
          props.selected?.to ? formatLocalDayKey(props.selected.to) : ''
        }`

  React.useEffect(() => {
    const anchor =
      mode === 'single' ? props.selected : (props.selected?.to ?? props.selected?.from)
    if (!anchor) return
    setView(new Date(anchor.getFullYear(), anchor.getMonth(), 1))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync month when selection keys change
  }, [selectedKey, mode])

  const cells = React.useMemo(() => buildMonthCells(view), [view])

  const shiftMonth = (delta: number) => {
    setView((v) => new Date(v.getFullYear(), v.getMonth() + delta, 1))
  }

  const handleDayClick = (day: Date) => {
    const clicked = startOfLocalDay(day)
    if (mode === 'single') {
      props.onSelect?.(clicked)
      return
    }
    if (!props.onSelect) return
    const selected = props.selected
    if (!selected?.from || (selected.from && selected.to)) {
      props.onSelect({ from: clicked, to: undefined })
      return
    }
    const start = startOfLocalDay(selected.from)
    if (clicked.getTime() < start.getTime()) {
      props.onSelect({ from: clicked, to: start })
    } else {
      props.onSelect({ from: start, to: clicked })
    }
  }

  return (
    <div className={cn('w-[280px] select-none p-2', className)}>
      <div className="mb-2 flex items-center justify-between gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => shiftMonth(-1)}
          aria-label="Предыдущий месяц"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <div className="text-sm font-medium capitalize">{monthLabel(view)}</div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => shiftMonth(1)}
          aria-label="Следующий месяц"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      <div className="mb-1 grid grid-cols-7 gap-0.5 text-center text-[11px] text-muted-foreground">
        {WEEKDAYS.map((d) => (
          <div key={d} className="py-1 font-medium uppercase">
            {d}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((day) => {
          const inMonth = day.getMonth() === view.getMonth()
          const outOfBounds = isOutsideBounds(day, fromDate, toDate)
          const fnDisabled = disabled?.(day) ?? false
          const muted = outOfBounds || !inMonth
          const clickDisabled = outOfBounds || fnDisabled
          const isSingleSelected =
            mode === 'single' && props.selected ? sameDay(day, props.selected) : false
          const isStart =
            mode === 'range' && props.selected?.from ? sameDay(day, props.selected.from) : false
          const isEnd =
            mode === 'range' && props.selected?.to ? sameDay(day, props.selected.to) : false
          const inRange = mode === 'range' ? isInSelectedRange(day, props.selected) : false
          const isToday = sameDay(day, new Date())

          return (
            <button
              key={day.toISOString()}
              type="button"
              disabled={clickDisabled}
              aria-disabled={clickDisabled || undefined}
              onClick={() => handleDayClick(day)}
              className={cn(
                'flex h-8 w-full items-center justify-center rounded-md text-sm transition-colors',
                muted && 'text-muted-foreground/40',
                outOfBounds && 'pointer-events-none',
                !clickDisabled && 'hover:bg-accent hover:text-accent-foreground',
                inRange && !isStart && !isEnd && 'bg-accent/60',
                (isStart || isEnd || isSingleSelected) &&
                  'bg-primary text-primary-foreground hover:bg-primary/90',
                isToday && !isStart && !isEnd && !isSingleSelected && 'ring-1 ring-primary/40',
                clickDisabled && 'cursor-not-allowed opacity-40',
              )}
            >
              {day.getDate()}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default Calendar
