import { PercentBar } from '@/components/ui/percent-bar'

/** Traffic share against the current filter maximum, with a percentage label. */
export default function ShareBar({ value, max }: { value: number; max: number }) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <PercentBar value={value} max={max} className="h-1.5 min-w-0 flex-1" />
      <span className="mono w-10 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground">
        {max > 0 ? Math.min((value / max) * 100, 100).toFixed(0) : '0'}%
      </span>
    </div>
  )
}
