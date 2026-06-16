import { Check, ChevronDown, History, Undo2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { CidrRuntimeBackup } from '@/types'
import { formatBackupLabel, formatBackupRelative, pluralFiles } from './utils'

interface RuntimeBackupsPanelProps {
  backups: CidrRuntimeBackup[]
  pipelineBusy: boolean
  recentRollbackStamp?: string | null
  onRollback: (stamp: string) => void
}

export default function RuntimeBackupsPanel({
  backups,
  pipelineBusy,
  recentRollbackStamp,
  onRollback,
}: RuntimeBackupsPanelProps) {
  const [expanded, setExpanded] = useState(false)

  const sorted = useMemo(
    () => [...backups].sort((a, b) => (b.mtime || 0) - (a.mtime || 0)),
    [backups],
  )

  useEffect(() => {
    if (recentRollbackStamp) {
      setExpanded(false)
    }
  }, [recentRollbackStamp])

  if (sorted.length === 0) return null

  const recentBackup = recentRollbackStamp
    ? sorted.find((b) => b.stamp === recentRollbackStamp)
    : null

  return (
    <div className="mt-4 rounded-md border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm font-medium">
            <History size={14} />
            Откат к предыдущей версии
            <Badge variant="secondary" className="font-normal">
              {sorted.length}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground max-w-xl">
            Копии создаются автоматически перед каждой сборкой. Откат восстанавливает файлы на
            контроллере и разворачивает их на узлы.
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-8 gap-1 text-xs"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Скрыть список' : 'Показать копии'}
          <ChevronDown size={14} className={cn('transition-transform', expanded && 'rotate-180')} />
        </Button>
      </div>

      {recentRollbackStamp && recentBackup && !expanded && (
        <div className="mt-3 flex items-start gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-900 dark:text-emerald-100">
          <Check size={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-medium">Откат выполнен</div>
            <div className="text-xs opacity-90">
              {formatBackupLabel(recentBackup.stamp, recentBackup.mtime)} ·{' '}
              {pluralFiles(recentBackup.file_count)} ·{' '}
              {formatBackupRelative(recentBackup.stamp, recentBackup.mtime)}
            </div>
          </div>
        </div>
      )}

      {!expanded && !recentRollbackStamp && (
        <p className="mt-3 text-xs text-muted-foreground">
          Последняя копия:{' '}
          <span className="text-foreground">
            {formatBackupLabel(sorted[0].stamp, sorted[0].mtime)}
          </span>
          {' · '}
          {formatBackupRelative(sorted[0].stamp, sorted[0].mtime)}
        </p>
      )}

      {expanded && (
        <div className="mt-3 rounded-md border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Дата и время</TableHead>
                <TableHead className="hidden sm:table-cell">Когда</TableHead>
                <TableHead className="text-right">Файлов</TableHead>
                <TableHead className="text-right w-[120px]">Действие</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((backup) => {
                const isRecent = backup.stamp === recentRollbackStamp
                return (
                  <TableRow
                    key={backup.stamp}
                    className={cn(isRecent && 'bg-emerald-500/5')}
                  >
                    <TableCell>
                      <div className="text-sm font-medium">
                        {formatBackupLabel(backup.stamp, backup.mtime)}
                      </div>
                      <div className="text-[11px] text-muted-foreground font-mono sm:hidden">
                        {backup.stamp}
                      </div>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
                      {formatBackupRelative(backup.stamp, backup.mtime)}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums">
                      {backup.file_count}
                    </TableCell>
                    <TableCell className="text-right">
                      {isRecent ? (
                        <Badge variant="default" className="font-normal">
                          Восстановлено
                        </Badge>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={pipelineBusy}
                          onClick={() => onRollback(backup.stamp)}
                        >
                          <Undo2 size={14} className="mr-1" />
                          Откатить
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
