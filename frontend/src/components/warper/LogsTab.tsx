import { useCallback, useEffect, useState } from 'react'
import { FileText, RefreshCw } from 'lucide-react'
import { getWarperLogs } from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { WarperHealthResponse } from '@/types'

interface LogsTabProps {
  health: WarperHealthResponse | null
  embedded?: boolean
  hideTitle?: boolean
}

export default function LogsTab({ health, embedded = false, hideTitle = false }: LogsTabProps) {
  const { activeNode } = useNode()
  const { error: notifyError } = useNotifications()
  const [lines, setLines] = useState<string[]>([])
  const [lineCount, setLineCount] = useState('200')
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!health?.installed) {
      setLines([])
      return
    }
    const count = Math.min(2000, Math.max(1, Number(lineCount) || 200))
    setLoading(true)
    try {
      const response = await getWarperLogs(count)
      setLines(response.lines ?? [])
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось загрузить логи')
      setLines([])
    } finally {
      setLoading(false)
    }
  }, [health?.installed, lineCount, notifyError])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  const filtered = filter.trim()
    ? lines.filter((line) => line.toLowerCase().includes(filter.trim().toLowerCase()))
    : lines

  const body = (
    <>
      <div className={`flex flex-col gap-2 sm:flex-row sm:flex-wrap ${embedded ? 'mb-3' : 'mb-4'}`}>
        <Input
          className="w-full sm:w-28"
          type="number"
          min={1}
          max={2000}
          value={lineCount}
          onChange={(e) => setLineCount(e.target.value)}
          disabled={!health?.installed || loading}
        />
        <Input
          className="w-full min-w-0 sm:min-w-[200px] sm:flex-1"
          placeholder="Фильтр по тексту..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <Button size="sm" className="w-full sm:w-auto" disabled={!health?.installed || loading} onClick={() => void load()}>
          <RefreshCw className="mr-1.5 h-4 w-4" />
          Обновить
        </Button>
      </div>

      {loading ? (
        <div className={`flex justify-center ${embedded ? 'py-6' : 'py-10'}`}>
          <Spinner />
        </div>
      ) : !health?.installed ? (
        <p className="text-sm text-muted-foreground">Логи доступны после установки AZ-WARP.</p>
      ) : (
        <pre
          className={`overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs leading-relaxed ${
            embedded ? 'max-h-56' : 'max-h-[28rem]'
          }`}
        >
          {filtered.length > 0 ? filtered.join('\n') : 'Нет строк логов.'}
        </pre>
      )}
    </>
  )

  if (embedded) {
    return <div>{!hideTitle && <h3 className="mb-3 text-sm font-semibold">Логи sing-box</h3>}{body}</div>
  }

  return (
    <StatusPanel title="Логи sing-box" icon={FileText}>
      {body}
    </StatusPanel>
  )
}
