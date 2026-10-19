import { ChevronDown, Download, Loader2, Server } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { BackgroundTask, BulkNodesAction } from '@/types'

type UsersBulkBarProps = {
  /** Сколько пользователей выбрано в списке. */
  selectedCount: number
  /** Идёт ли сейчас массовая операция (одна за раз). */
  busy: boolean
  /** Текущая задача массовой операции — прогресс и отчёт. */
  task: BackgroundTask | null
  onAction: (action: BulkNodesAction) => void
  onDownloadReport: (taskId: string) => void
}

const MENU_ITEMS: { id: BulkNodesAction; label: string }[] = [
  { id: 'add', label: 'Добавить сервер…' },
  { id: 'remove', label: 'Убрать сервер…' },
  { id: 'replace', label: 'Перенести на другой…' },
]

/** Панель массовых операций с серверами над списком пользователей. */
export default function UsersBulkBar({
  selectedCount,
  busy,
  task,
  onAction,
  onDownloadReport,
}: UsersBulkBarProps) {
  const running = task?.status === 'queued' || task?.status === 'running'
  const finished = task?.status === 'completed' || task?.status === 'failed'

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 p-2">
      <span className="text-xs text-muted-foreground">
        {selectedCount > 0 ? `Выбрано: ${selectedCount}` : 'Выбрано: 0'}
      </span>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" size="sm" variant="outline" className="h-7 text-xs" disabled={busy}>
            <Server size={12} />
            Серверы
            <ChevronDown size={12} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          {MENU_ITEMS.map((item) => (
            <DropdownMenuItem key={item.id} disabled={busy} onClick={() => onAction(item.id)}>
              <Server size={14} />
              {item.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {running && task && (
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 size={12} className="animate-spin" />
          {task.progress_stage || task.message || 'Массовая операция выполняется…'}
        </span>
      )}

      {finished && task && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => onDownloadReport(task.task_id)}
        >
          <Download size={12} />
          Скачать отчёт
        </Button>
      )}
    </div>
  )
}
