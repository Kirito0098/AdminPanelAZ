import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import { ApiError, checkWarperUpdates, openWarperUpdateStream } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { WarperHealthResponse, WarperUpdatesCheckResponse } from '@/types'
import { isWarperDisabled } from './utils'
import WarperSection from './WarperSection'

interface WarperUpdatesSectionProps {
  health: WarperHealthResponse | null
}

export default function WarperUpdatesSection({ health }: WarperUpdatesSectionProps) {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const disabled = isWarperDisabled(health)
  const streamRef = useRef<EventSource | null>(null)

  const [info, setInfo] = useState<WarperUpdatesCheckResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [logLines, setLogLines] = useState<string[]>([])

  const closeStream = useCallback(() => {
    streamRef.current?.close()
    streamRef.current = null
  }, [])

  useEffect(() => () => closeStream(), [closeStream, activeNode?.id])

  const load = useCallback(async (force = false) => {
    setLoading(true)
    try {
      setInfo(await checkWarperUpdates(force))
    } catch (err) {
      setInfo(null)
      notifyError(err instanceof ApiError ? err.message : 'Ошибка проверки обновлений AZ-WARP')
    } finally {
      setLoading(false)
    }
  }, [notifyError])

  useEffect(() => {
    if (!disabled) {
      void load()
    } else {
      setInfo(null)
    }
  }, [disabled, load, activeNode?.id])

  const handleUpdate = () => {
    confirm({
      title: 'Обновить AZ-WARP на узле?',
      description: 'Будет загружена новая версия WARPER с GitHub. Процесс может занять несколько минут.',
      alert: {
        variant: 'warning',
        title: 'Внимание',
        children:
          'На время обновления AZ-WARP может быть недоступен. Не закрывайте страницу до завершения — лог отображается ниже.',
      },
      confirmLabel: 'Обновить AZ-WARP',
      destructive: true,
      onConfirm: async () => {
        closeStream()
        setUpdating(true)
        setLogLines([])
        const source = openWarperUpdateStream(
          (event) => {
            if (event.event === 'log' && event.line) {
              setLogLines((prev) => [...prev, event.line])
            }
            if (event.event === 'done') {
              closeStream()
              setUpdating(false)
              if (event.success) {
                success('AZ-WARP успешно обновлён')
              } else {
                notifyError(`Обновление завершилось с кодом ${event.return_code ?? '—'}`)
              }
              void load(true)
            }
            if (event.event === 'error') {
              closeStream()
              setUpdating(false)
              notifyError(event.detail || 'Ошибка обновления AZ-WARP')
            }
          },
          (message) => {
            closeStream()
            setUpdating(false)
            notifyError(message)
          },
        )
        if (!source) {
          setUpdating(false)
          notifyError('Не удалось открыть поток обновления')
          return
        }
        streamRef.current = source
      },
    })
  }

  return (
    <>
      <ConfirmDialogHost dialogProps={dialogProps} />
      <InlineProgressBar active={updating} label="Обновление AZ-WARP..." />

      <WarperSection
        title="Обновление AZ-WARP"
        icon={Download}
        description="Проверка и установка новой версии WARPER на активном узле"
      >
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" disabled={disabled || loading || updating} onClick={() => void load(true)}>
              <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Проверить
            </Button>
            {info?.update_available ? (
              <Badge variant="destructive">
                Доступно {info.remote ?? 'новая версия'}
              </Badge>
            ) : info ? (
              <Badge variant="secondary">Актуально ({info.current ?? health?.version ?? '—'})</Badge>
            ) : null}
          </div>

          {info && (
            <div className="grid gap-3 rounded-md border bg-muted/30 p-4 text-sm md:grid-cols-2">
              <div>
                <span className="text-muted-foreground">Текущая: </span>
                <code className="font-mono text-xs">{info.current ?? health?.version ?? '—'}</code>
              </div>
              <div>
                <span className="text-muted-foreground">Доступная: </span>
                <code className="font-mono text-xs">{info.remote ?? '—'}</code>
              </div>
            </div>
          )}

          {info?.message && !info.error && (
            <p className="text-sm text-muted-foreground">{info.message}</p>
          )}

          {info?.error && (
            <p className="text-sm text-destructive">{info.error}</p>
          )}

          {info?.update_available && (
            <Button variant="destructive" size="sm" disabled={disabled || updating} onClick={handleUpdate}>
              {updating ? 'Обновление...' : 'Установить обновление'}
            </Button>
          )}

          {logLines.length > 0 && (
            <pre className="max-h-64 overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-xs leading-relaxed">
              {logLines.join('\n')}
            </pre>
          )}
        </div>
      </WarperSection>
    </>
  )
}
