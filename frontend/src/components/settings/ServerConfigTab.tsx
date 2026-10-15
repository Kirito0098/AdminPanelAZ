import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Wrench } from 'lucide-react'
import { ApiError, applyServerConfig, getServerConfigPreview } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { SettingsToolbar } from '@/components/settings/SettingsChrome'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import type { ServerConfigDetail, ServerConfigPreview, ServerConfigRow } from '@/types'

const STATUS_BADGE: Record<ServerConfigRow['status'], 'success' | 'secondary' | 'destructive'> = {
  ok: 'success',
  пропущен: 'secondary',
  ошибка: 'destructive',
}

function DetailLines({ sign, lines, className }: { sign: string; lines: string[]; className: string }) {
  return lines.map((line) => (
    <div key={sign + line} className={className}>
      <span aria-hidden="true" className="select-none pr-2">
        {sign}
      </span>
      {line}
    </div>
  ))
}

function ItemDetail({ detail }: { detail: ServerConfigDetail }) {
  const diff = detail.removed.length + detail.added.length > 0
  return (
    <div className="mt-1.5 space-y-2">
      {diff ? (
        <div className="overflow-x-auto rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs leading-relaxed">
          <DetailLines sign="−" lines={detail.removed} className="whitespace-pre text-destructive" />
          <DetailLines sign="+" lines={detail.added} className="whitespace-pre text-emerald-600 dark:text-emerald-400" />
        </div>
      ) : null}
      {detail.info.length ? (
        <ul className="space-y-0.5 text-foreground/80">
          {detail.info.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {detail.why.map((line) => (
        <p key={line}>
          <span className="font-medium text-foreground">Почему это важно: </span>
          {line}
        </p>
      ))}
    </div>
  )
}

function Section({ title, items, details = {} }: { title: string; items: string[]; details?: Record<string, ServerConfigDetail> }) {
  if (!items.length) return null
  return (
    <section className="space-y-1.5">
      <h4 className="text-sm font-semibold">{title}</h4>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground marker:text-muted-foreground/60">
        {items.map((item) => (
          <li key={item}>
            {item}
            {details[item] ? <ItemDetail detail={details[item]} /> : null}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function ServerConfigTab() {
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [preview, setPreview] = useState<ServerConfigPreview | null>(null)
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState(false)
  const [rows, setRows] = useState<ServerConfigRow[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      setPreview(await getServerConfigPreview())
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : 'Не удалось проверить сервер')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const finish = (resultRows: ServerConfigRow[], ok: boolean, message: string) => {
    setApplying(false)
    setRows(resultRows)
    if (ok) success(message)
    else notifyError(message)
    void load()
  }

  const handleApply = () => {
    confirm({
      title: 'Обновить настройки сервера?',
      description: 'Применится всё, что указано в разделах «Добавится» и «Изменится».',
      alert: {
        variant: 'info',
        title: 'Панель продолжит работать',
        children: preview?.sections.effect.join('. ') || 'Панель и агенты не перезапускаются.',
      },
      confirmLabel: 'Применить',
      onConfirm: async () => {
        setApplying(true)
        setRows([])
        try {
          const resp = await applyServerConfig()
          trackBackgroundTask(resp.task_id, {
            onComplete: (task) => {
              const result = task.result as { success?: boolean; message?: string; rows?: ServerConfigRow[] } | undefined
              finish(result?.rows ?? [], Boolean(result?.success), result?.message || 'Настройки сервера обновлены')
            },
            onError: (_task, message) => finish([], false, message || 'Не удалось обновить настройки сервера'),
          })
        } catch (err) {
          setApplying(false)
          notifyError(err instanceof ApiError ? err.message : 'Не удалось запустить обновление настроек')
        }
      },
    })
  }

  const pending = preview?.pending ?? 0
  const sections = preview?.sections

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <SettingsToolbar
        title="Настройки сервера"
        meta="То, что обновление через панель не меняет: nginx, системные пакеты, команда adminpanelaz, службы"
        actions={
          <>
            {preview && !loading ? (
              <Badge variant={pending ? 'warning' : 'success'}>{pending ? `Нужно обновить: ${pending}` : 'Всё актуально'}</Badge>
            ) : null}
            <Button variant="outline" size="sm" className="gap-2" onClick={() => void load()} disabled={loading || applying}>
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Проверить снова
            </Button>
            {pending > 0 ? (
              <Button size="sm" className="gap-2" onClick={handleApply} disabled={loading || applying}>
                <Wrench size={14} />
                {applying ? 'Применяем…' : 'Применить'}
              </Button>
            ) : null}
          </>
        }
      />

      {rows.length > 0 ? (
        <Card className="shadow-sm">
          <CardContent className="space-y-2 pt-6">
            <h4 className="text-sm font-semibold">Итог</h4>
            <ul className="space-y-1.5">
              {rows.map((row) => (
                <li key={row.step} className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="w-32 shrink-0 font-medium">{row.label}</span>
                  <Badge variant={STATUS_BADGE[row.status]}>{row.status}</Badge>
                  {row.detail ? <span className="min-w-0 text-muted-foreground">{row.detail}</span> : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {loading && !preview ? <Spinner label="Проверяем сервер..." className="py-10" /> : null}

      {loadError ? (
        <SettingsAlert variant="danger" title="Не удалось проверить сервер">
          {loadError}
        </SettingsAlert>
      ) : null}

      {sections ? (
        <Card className="shadow-sm">
          <CardContent className="space-y-5 pt-6">
            {pending === 0 ? (
              <p className="text-sm">Всё, что можно обновить отсюда, уже в актуальном состоянии.</p>
            ) : null}
            <Section title="Добавится" items={sections.add} />
            <Section
              title="Изменится"
              items={pending > 0 ? [...sections.change, ...sections.recheck] : []}
              details={preview.details}
            />
            <Section title="Не изменится" items={sections.keep} />
            {pending > 0 ? (
              <>
                <Section title="Удалится" items={sections.remove} />
                <Section title="Как это повлияет" items={sections.effect} />
              </>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
