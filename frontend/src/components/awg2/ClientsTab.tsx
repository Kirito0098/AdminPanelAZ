import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Columns2, Download, Loader2, Plus, RefreshCw, Shield, Trash2, Users } from 'lucide-react'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import {
  formatCreatedAt,
  getDownloadFilename,
  hasAzProfiles,
  hasVpnProfiles,
  pickAzFile,
  pickVpnFile,
} from '@/lib/configCardUtils'
import {
  GRID_COLS_OPTIONS,
  gridColsClass,
  type CardGridCols,
} from '@/lib/configCardViewPrefs'
import { parseContentDispositionFilename } from '@/lib/profileDownloadName'
import { cn } from '@/lib/utils'
import type { Awg2HealthResponse, VpnConfig } from '@/types'

interface ClientsTabProps {
  health: Awg2HealthResponse | null
}

const CLIENT_NAME_RE = /^[a-zA-Z0-9_-]{1,32}$/
const GRID_STORAGE_KEY = 'awg2-clients:gridCols'
const GRID_COLS_ALLOWED: readonly CardGridCols[] = ['auto', '1', '2', '3', '4']

function loadAwg2GridCols(): CardGridCols {
  if (typeof window === 'undefined') return 'auto'
  try {
    const value = window.localStorage.getItem(GRID_STORAGE_KEY)
    return value && (GRID_COLS_ALLOWED as readonly string[]).includes(value)
      ? (value as CardGridCols)
      : 'auto'
  } catch {
    return 'auto'
  }
}

function saveAwg2GridCols(cols: CardGridCols) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(GRID_STORAGE_KEY, cols)
  } catch {
    /* ignore quota / privacy mode */
  }
}

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
  const [downloadBusyId, setDownloadBusyId] = useState<number | null>(null)
  const [gridCols, setGridCols] = useState<CardGridCols>('auto')

  const ready = Boolean(health?.installed)

  useEffect(() => {
    setGridCols(loadAwg2GridCols())
  }, [])

  const handleGridColsChange = (cols: CardGridCols) => {
    setGridCols(cols)
    saveAwg2GridCols(cols)
  }

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
    setDownloadBusyId(config.id)
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
    } finally {
      setDownloadBusyId(null)
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
                Конфигурации AmneziaWG 2.0 на текущем узле. Создание, удаление и скачивание — те же API, что в
                Конфигурациях.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 self-start">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  title="Столбцы карточек"
                  aria-label="Столбцы карточек"
                >
                  <Columns2 className="h-4 w-4" />
                  {GRID_COLS_OPTIONS.find((option) => option.value === gridCols)?.label ?? 'Авто'}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 p-3">
                <DropdownMenuLabel className="px-0 text-xs font-medium text-muted-foreground">
                  Столбцы
                </DropdownMenuLabel>
                <div className="flex flex-wrap items-center gap-1 rounded-xl border bg-muted/30 p-1">
                  {GRID_COLS_OPTIONS.map((option) => (
                    <Button
                      key={option.value}
                      type="button"
                      size="sm"
                      variant={gridCols === option.value ? 'default' : 'ghost'}
                      className="h-7 flex-1 px-2 text-xs"
                      onClick={() => handleGridColsChange(option.value)}
                    >
                      {option.label}
                    </Button>
                  ))}
                </div>
                <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
                  «Авто» — 1→2→3→4 колонки по ширине экрана.
                </p>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
              Обновить
            </Button>
          </div>
        </div>

        <form
          className="mt-4 grid gap-3 rounded-lg border bg-background/60 p-4 sm:grid-cols-2 xl:grid-cols-4"
          onSubmit={handleCreate}
        >
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
        <div className={cn('grid items-stretch gap-3', gridColsClass(gridCols))}>
          {Array.from({ length: 4 }).map((_, index) => (
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
        <div className={cn('grid items-stretch gap-3', gridColsClass(gridCols))}>
          {clients.map((config) => {
            const tab = 'amneziawg2' as const
            const vpnFile = pickVpnFile(config, tab)
            const azFile = pickAzFile(config, tab)
            const hasBoth = hasVpnProfiles(config, tab) && hasAzProfiles(config, tab)
            const busy = downloadBusyId === config.id

            return (
              <div key={config.id} className="flex flex-col rounded-xl border bg-card/50 p-4 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="truncate text-base font-semibold">{config.client_name}</h3>
                      <Badge variant="outline">AWG2</Badge>
                      {hasVpnProfiles(config, tab) && (
                        <Badge className="bg-sky-600/90 text-white hover:bg-sky-600/90">VPN</Badge>
                      )}
                      {hasAzProfiles(config, tab) && (
                        <Badge className="bg-orange-600/90 text-white hover:bg-orange-600/90">AntiZapret</Badge>
                      )}
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
                    <dd>{formatCreatedAt(config.created_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Срок сертификата</dt>
                    <dd>{config.cert_expire_days ? `${config.cert_expire_days} дн.` : '—'}</dd>
                  </div>
                </dl>

                <div className="mt-auto space-y-2 border-t border-border/60 pt-2.5">
                  {vpnFile || azFile ? (
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {hasBoth ? (
                        <>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-8 min-w-0 flex-1 gap-1.5 px-2 text-xs text-sky-600"
                            title={`Скачать VPN: ${getDownloadFilename(config, vpnFile!)}`}
                            disabled={busy}
                            onClick={() =>
                              void handleDownload(config, vpnFile!.path, getDownloadFilename(config, vpnFile!))
                            }
                          >
                            {busy ? (
                              <Loader2 size={14} className="shrink-0 animate-spin" />
                            ) : (
                              <Download size={14} className="shrink-0" />
                            )}
                            <span className="truncate">VPN</span>
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-8 min-w-0 flex-1 gap-1.5 px-2 text-xs text-orange-600"
                            title={`Скачать AntiZapret: ${getDownloadFilename(config, azFile!)}`}
                            disabled={busy}
                            onClick={() =>
                              void handleDownload(config, azFile!.path, getDownloadFilename(config, azFile!))
                            }
                          >
                            {busy ? (
                              <Loader2 size={14} className="shrink-0 animate-spin" />
                            ) : (
                              <Download size={14} className="shrink-0" />
                            )}
                            <span className="truncate">AntiZapret</span>
                          </Button>
                        </>
                      ) : (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-8 min-w-0 gap-1.5 px-2 text-xs sm:col-span-2"
                          title={`Скачать: ${getDownloadFilename(config, (vpnFile || azFile)!)}`}
                          disabled={busy}
                          onClick={() => {
                            const file = (vpnFile || azFile)!
                            void handleDownload(config, file.path, getDownloadFilename(config, file))
                          }}
                        >
                          {busy ? (
                            <Loader2 size={14} className="shrink-0 animate-spin" />
                          ) : (
                            <Download size={14} className="shrink-0" />
                          )}
                          <span className="truncate">Скачать</span>
                        </Button>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Файлы появятся после генерации профиля на сервере.
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title="Удалить клиента?"
        description={
          deleteTarget ? `Клиент «${deleteTarget.client_name}» будет удалён вместе с конфигурацией.` : undefined
        }
        icon={Trash2}
        destructive
        confirmLabel="Удалить"
        loading={deleting}
        onConfirm={handleDelete}
      />
    </div>
  )
}
