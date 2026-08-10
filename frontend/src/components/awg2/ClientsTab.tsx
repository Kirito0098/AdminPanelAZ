import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Download, Loader2, Plus, RefreshCw, Shield, Trash2, Users } from 'lucide-react'
import {
  ApiError,
  createConfig,
  deleteConfig,
  downloadProfile,
  getConfigs,
} from '@/api/client'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { formatDate } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import { parseContentDispositionFilename } from '@/lib/profileDownloadName'
import type { Awg2HealthResponse, VpnConfig } from '@/types'

interface ClientsTabProps {
  health: Awg2HealthResponse | null
}

const CLIENT_NAME_RE = /^[a-zA-Z0-9_-]{1,32}$/

function sortClients(items: VpnConfig[]): VpnConfig[] {
  return [...items].sort((a, b) => b.created_at.localeCompare(a.created_at))
}

export default function ClientsTab({ health }: ClientsTabProps) {
  const { success, error: notifyError } = useNotifications()
  const { withInline } = useProgress()
  const [clients, setClients] = useState<VpnConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [clientName, setClientName] = useState('')
  const [description, setDescription] = useState('')
  const [certDays, setCertDays] = useState(3650)
  const [submitting, setSubmitting] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<VpnConfig | null>(null)
  const [deleting, setDeleting] = useState(false)

  const ready = Boolean(health?.installed)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getConfigs(true)
      setClients(sortClients(data.filter((config) => config.vpn_type === 'amneziawg2')))
    } catch (err) {
      setClients([])
      setLoadError(err instanceof Error ? err.message : 'Не удалось загрузить клиентов')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!ready) return
    void load()
  }, [load, ready])

  const clientCount = useMemo(() => clients.length, [clients.length])

  const resetForm = () => {
    setClientName('')
    setDescription('')
    setCertDays(3650)
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()

    const trimmedName = clientName.trim()
    if (!trimmedName) {
      notifyError('Укажите имя клиента')
      return
    }
    if (!CLIENT_NAME_RE.test(trimmedName)) {
      notifyError('Имя: латиница, цифры, _ и -, до 32 символов')
      return
    }
    if (!Number.isFinite(certDays) || certDays < 1 || certDays > 3650) {
      notifyError('Срок сертификата: от 1 до 3650 дней')
      return
    }

    setSubmitting(true)
    try {
      await withInline(async () => {
        await createConfig({
          client_name: trimmedName,
          vpn_type: 'amneziawg2',
          cert_expire_days: certDays,
          description: description.trim() || undefined,
        })
        await load()
      }, 'Создание клиента...')
      resetForm()
      success(`Клиент «${trimmedName}» создан`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания клиента')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDownload = async (config: VpnConfig, path: string, filename: string) => {
    let downloadName = filename
    try {
      await withInline(async () => {
        const response = await downloadProfile(config.id, path)
        if (!response.ok) throw new Error('Ошибка скачивания')
        const blob = await response.blob()
        downloadName = parseContentDispositionFilename(response.headers.get('Content-Disposition')) ?? downloadName
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = downloadName
        link.click()
        URL.revokeObjectURL(url)
      }, 'Скачивание файла...')
      success(`Файл «${downloadName}» скачан`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка скачивания файла')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await withInline(async () => {
        await deleteConfig(deleteTarget.id)
        await load()
      }, 'Удаление клиента...')
      success(`Клиент «${deleteTarget.client_name}» удалён`)
      setDeleteTarget(null)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления клиента')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border bg-card/50 p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-semibold tracking-tight">Клиенты AZ-AWG2</h2>
                <Badge variant="secondary">{clientCount}</Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Конфигурации AmneziaWG2 на текущем узле. Создание, удаление и скачивание используют обычные API конфигураций.
              </p>
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5 self-start"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            Обновить
          </Button>
        </div>

        <form className="mt-4 grid gap-3 rounded-lg border bg-background/60 p-4 sm:grid-cols-2 xl:grid-cols-4" onSubmit={handleCreate}>
          <div className="space-y-2">
            <Label htmlFor="awg2-client-name">Имя клиента</Label>
            <Input
              id="awg2-client-name"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              placeholder="client-name"
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="awg2-cert-days">Срок сертификата, дней</Label>
            <Input
              id="awg2-cert-days"
              type="number"
              min={1}
              max={3650}
              value={certDays}
              onChange={(e) => setCertDays(Number(e.target.value))}
            />
          </div>
          <div className="space-y-2 sm:col-span-2 xl:col-span-1">
            <Label htmlFor="awg2-description">Описание</Label>
            <Input
              id="awg2-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Необязательно"
              autoComplete="off"
            />
          </div>
          <div className="flex items-end sm:col-span-2 xl:col-span-1">
            <Button type="submit" className="w-full gap-1.5" disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Создать клиента
            </Button>
          </div>
        </form>
      </div>

      {loadError && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {loadError}
        </div>
      )}

      {loading ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <div key={index} className="rounded-xl border bg-card/50 p-4">
              <div className="flex items-center gap-3">
                <Skeleton className="h-10 w-10 rounded-xl" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-5 w-40" />
                  <Skeleton className="h-4 w-56" />
                </div>
              </div>
              <div className="mt-4 space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
              </div>
            </div>
          ))}
        </div>
      ) : clients.length === 0 ? (
        <div className="rounded-xl border bg-card/50 p-6">
          <EmptyState
            icon={Users}
            title="Клиентов пока нет"
            description="Создайте первый AZ-AWG2 профиль, чтобы здесь появились ссылки на скачивание и управление."
          />
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {clients.map((config) => (
            <div key={config.id} className="rounded-xl border bg-card/50 p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-base font-semibold">{config.client_name}</h3>
                    <Badge variant="outline">AWG2</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {config.description?.trim() || 'Без описания'}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="shrink-0 text-destructive hover:text-destructive"
                  onClick={() => setDeleteTarget(config)}
                  title="Удалить клиента"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">Создан</dt>
                  <dd>{formatDate(config.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Срок сертификата</dt>
                  <dd>{config.cert_expire_days ? `${config.cert_expire_days} дн.` : '—'}</dd>
                </div>
              </dl>

              <div className="mt-4 space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Файлы профиля
                </p>
                {config.profile_files?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {config.profile_files.map((file) => (
                      <Button
                        key={`${config.id}:${file.path}`}
                        type="button"
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        onClick={() => void handleDownload(config, file.path, file.download_filename ?? file.filename)}
                      >
                        <Download className="h-3.5 w-3.5" />
                        <span className="max-w-[16rem] truncate">{file.download_filename ?? file.filename}</span>
                      </Button>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Файлы появятся после генерации профиля на сервере.</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title="Удалить клиента?"
        description={deleteTarget ? `Клиент «${deleteTarget.client_name}» будет удалён вместе с конфигурацией.` : undefined}
        icon={Trash2}
        destructive
        confirmLabel="Удалить"
        loading={deleting}
        onConfirm={handleDelete}
      />
    </div>
  )
}
