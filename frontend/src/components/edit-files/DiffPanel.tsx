import type { DiffMode, DiffOp } from '@/lib/buildLightDiff'
import { cn } from '@/lib/utils'

type DiffPanelProps = {
  ops: DiffOp[]
  mode: DiffMode
  maxLines?: number
  compact?: boolean
  className?: string
}

export default function DiffPanel({
  ops,
  mode,
  maxLines = 300,
  compact = false,
  className,
}: DiffPanelProps) {
  if (!ops.length) {
    return (
      <div className={cn('text-sm text-muted-foreground', className)}>
        Изменений не найдено.
      </div>
    )
  }

  const visibleOps = ops.slice(0, maxLines)
  const hasMore = ops.length > maxLines

  return (
    <div
      className={cn(
        'rounded-lg border border-zinc-700/80 bg-zinc-950/80',
        compact ? 'p-2' : 'p-2.5',
        className,
      )}
    >
      <div
        className={cn(
          'grid gap-1 overflow-auto',
          compact ? 'max-h-40' : 'max-h-56',
        )}
      >
        {visibleOps.map((op, index) => (
          <div
            key={`${op.type}-${op.lineNumber}-${index}`}
            className={cn(
              'flex flex-col gap-1 rounded-md border px-2 py-1 font-mono text-xs leading-relaxed sm:grid sm:grid-cols-[auto_auto_minmax(0,1fr)] sm:items-start sm:gap-2',
              op.type === 'add'
                ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-100'
                : 'border-red-500/50 bg-red-500/20 text-red-100',
            )}
          >
            <span
              className={cn(
                'w-3 text-center font-bold',
                op.type === 'add' ? 'text-emerald-400' : 'text-red-400',
              )}
            >
              {op.type === 'add' ? '+' : '-'}
            </span>
            <span className="pt-px text-[10px] tabular-nums text-muted-foreground">
              L{op.lineNumber}
            </span>
            <span className="whitespace-pre-wrap break-words">{op.text || ' '}</span>
          </div>
        ))}
      </div>

      {hasMore && (
        <p className="mt-2 text-xs text-muted-foreground">
          Показаны первые {maxLines} строк diff.
        </p>
      )}

      {mode === 'indexed' && (
        <p className="mt-2 text-xs text-muted-foreground">
          Для большого файла включен быстрый режим diff.
        </p>
      )}
    </div>
  )
}
