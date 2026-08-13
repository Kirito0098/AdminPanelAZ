import { useCallback, useEffect, useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Ban,
  ArrowRightLeft,
  FileEdit,
  GitCompare,
  Globe,
  HelpCircle,
  Loader2,
  Network,
  RefreshCw,
  RotateCcw,
  Save,
  ShieldBan,
  ShieldCheck,
  WifiOff,
  Zap,
} from 'lucide-react'
import { Navigate, useSearchParams } from 'react-router-dom'
import {
  ApiError,
  getEditFileContent,
  getEditFiles,
  saveEditFile,
  saveEditFilesBatch,
  transferEditFiles,
} from '@/api/client'
import DiffPanel from '@/components/edit-files/DiffPanel'
import TransferFilesDialog from '@/components/edit-files/TransferFilesDialog'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import { NodeBadge } from '@/components/NodeSelector'
import { SettingsCollapsible } from '@/components/settings/SettingsChrome'
import SettingsAlert from '@/components/settings/SettingsAlert'
import ConfirmDialog, { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import HaReplicaBanner from '@/components/dashboard/HaReplicaBanner'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useHaReplicaReadonly } from '@/hooks/useHaReplicaReadonly'
import {
  buildLightDiff,
  countDiffOps,
} from '@/lib/buildLightDiff'
import { ALL_NODES_ONLINE_PHRASE } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import type { EditFileEntry } from '@/types'

const EDITOR_TEXTAREA_CLASS =
  'min-h-[16rem] resize-y border-zinc-800 bg-zinc-950 font-mono text-sm leading-relaxed text-zinc-200 placeholder:text-zinc-500 focus-visible:ring-zinc-700 sm:min-h-[22rem] lg:min-h-[28rem]'

type FileGroup = 'hosts' | 'ips' | 'adblock'

type FileMeta = {
  description: string
  hint: string
  placeholder: string
  icon: LucideIcon
  group: FileGroup
}

const FILE_META: Record<string, FileMeta> = {
  include_hosts: {
    description: 'Сайты, которые должны идти через VPN',
    hint: 'Например: youtube.com, twitter.com',
    placeholder: 'youtube.com\nexample.com\n\nОдин сайт — одна строка',
    icon: Globe,
    group: 'hosts',
  },
  exclude_hosts: {
    description: 'Сайты, которые не нужно пускать через VPN',
    hint: 'Локальные и внутренние ресурсы',
    placeholder: 'bank.local\nintranet.company.ru\n\nОдин сайт — одна строка',
    icon: Globe,
    group: 'hosts',
  },
  remove_hosts: {
    description: 'Убрать сайт из автоматически собранных списков',
    hint: 'Если сайт попал в список по ошибке',
    placeholder: 'unwanted-site.com\n\nОдин сайт — одна строка',
    icon: Globe,
    group: 'hosts',
  },
  include_ips: {
    description: 'IP-адреса, которые направлять через VPN',
    hint: 'Можно указать диапазон: 10.0.0.0/24',
    placeholder: '10.0.0.0/24\n203.0.113.5\n\nОдин адрес или диапазон — одна строка',
    icon: Network,
    group: 'ips',
  },
  exclude_ips: {
    description: 'IP-адреса вне маршрутизации VPN',
    hint: 'Локальная сеть и служебные адреса',
    placeholder: '192.168.0.0/24\n\nОдин адрес или диапазон — одна строка',
    icon: Network,
    group: 'ips',
  },
  allow_ips: {
    description: 'Кому разрешён доступ к серверу',
    hint: 'Белый список доверенных адресов',
    placeholder: '203.0.113.10\n\nОдин IP — одна строка',
    icon: ShieldCheck,
    group: 'ips',
  },
  drop_ips: {
    description: 'Заблокировать исходящие подключения на эти адреса',
    hint: 'Трафик на эти IP не уйдёт с сервера',
    placeholder: '0.0.0.0/0\n\nОдин адрес или диапазон — одна строка',
    icon: ShieldBan,
    group: 'ips',
  },
  forward_ips: {
    description: 'Перенаправить трафик на эти адреса через VPN',
    hint: 'Для отдельных IP вне списков доменов',
    placeholder: '8.8.8.8\n1.1.1.1\n\nОдин IP — одна строка',
    icon: Zap,
    group: 'ips',
  },
  deny_ips: {
    description: 'Запретить входящие подключения с этих адресов',
    hint: 'Защита от нежелательных клиентов',
    placeholder: '198.51.100.0/24\n\nОдин адрес или диапазон — одна строка',
    icon: Ban,
    group: 'ips',
  },
  include_adblock_hosts: {
    description: 'Дополнительно блокировать рекламу на этих сайтах',
    hint: 'Расширяет стандартный список блокировки',
    placeholder: 'ads.example.com\ntracker.site\n\nОдин сайт — одна строка',
    icon: ShieldBan,
    group: 'adblock',
  },
  exclude_adblock_hosts: {
    description: 'Не блокировать рекламу на этих сайтах',
    hint: 'Исключения из фильтра рекламы',
    placeholder: 'my-site.com\n\nОдин сайт — одна строка',
    icon: ShieldCheck,
    group: 'adblock',
  },
}

const GROUP_LABELS: Record<FileGroup, string> = {
  hosts: 'Сайты',
  ips: 'IP-адреса',
  adblock: 'Блокировка рекламы',
}

const DEFAULT_FILE_META: FileMeta = {
  description: 'Список настроек VPN',
  hint: 'По одной записи на строку',
  placeholder: 'Введите значения — по одному на строку',
  icon: FileEdit,
  group: 'hosts',
}

function lineCount(text: string) {
  if (!text) return 0
  return text.split('\n').length
}

function getFileMeta(key: string): FileMeta {
  return FILE_META[key] ?? DEFAULT_FILE_META
}

export default function EditFilesPage() {
  const { user } = useAuth()
  const { activeNode, activeNodeHa, nodes } = useNode()
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal, withInline } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const haReplicaReadonly = useHaReplicaReadonly()
  const [searchParams] = useSearchParams()

  const [files, setFiles] = useState<EditFileEntry[]>([])
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [fileLoading, setFileLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [confirmApply, setConfirmApply] = useState(false)
  const [diffOpen, setDiffOpen] = useState(false)
  const [diffBaseline, setDiffBaseline] = useState<'saved' | 'disk'>('saved')
  const [diskContent, setDiskContent] = useState<string | null>(null)
  const [diskCompareLoading, setDiskCompareLoading] = useState(false)
  const [transferOpen, setTransferOpen] = useState(false)
  const [transferLoading, setTransferLoading] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  const nodeOffline = activeNode?.status === 'offline'
  const nodeReadonly = nodeOffline || haReplicaReadonly
  const nodeUnknown = activeNode?.status === 'unknown'
  const isAdmin = user?.role === 'admin'
  const isHaAutoPrimary =
    activeNodeHa?.role === 'primary' && activeNodeHa.sync_mode === 'auto'
  const isHaReplica = activeNodeHa?.role === 'replica'
  const showTransferButton = isAdmin && nodes.length > 1 && !isHaReplica
  const hasUnsavedChanges = content !== savedContent

  const active = files.find((f) => f.key === activeKey)
  const activeMeta = activeKey ? getFileMeta(activeKey) : null
  const ActiveIcon = activeMeta?.icon ?? FileEdit

  const groupedFiles = useMemo(() => {
    const groups: Record<FileGroup, EditFileEntry[]> = { hosts: [], ips: [], adblock: [] }
    for (const file of files) {
      const group = getFileMeta(file.key).group
      groups[group].push(file)
    }
    return groups
  }, [files])

  const stats = useMemo(() => {
    const bytes = new TextEncoder().encode(content).length
    return { lines: lineCount(content), bytes }
  }, [content])

  const liveDiff = useMemo(() => buildLightDiff(savedContent, content), [savedContent, content])
  const diskDiff = useMemo(
    () => (diskContent != null ? buildLightDiff(diskContent, content) : null),
    [diskContent, content],
  )
  const activeDiff =
    diffBaseline === 'disk' && diskDiff != null ? diskDiff : liveDiff
  const liveDiffCounts = useMemo(() => countDiffOps(liveDiff.ops), [liveDiff.ops])
  const activeDiffCounts = useMemo(() => countDiffOps(activeDiff.ops), [activeDiff.ops])

  const diffSummaryText = useMemo(() => {
    if (diffBaseline === 'disk' && diskContent != null) {
      if (!activeDiffCounts.added && !activeDiffCounts.removed) {
        return 'Совпадает с версией на сервере'
      }
      return `На сервере: +${activeDiffCounts.added} / −${activeDiffCounts.removed} строк`
    }
    if (!liveDiffCounts.added && !liveDiffCounts.removed) {
      return 'Изменений пока нет'
    }
    return `Добавлено ${liveDiffCounts.added}, удалено ${liveDiffCounts.removed}`
  }, [activeDiffCounts, diffBaseline, diskContent, liveDiffCounts])

  const resetDiffBaseline = useCallback(() => {
    setDiffBaseline('saved')
    setDiskContent(null)
  }, [])

  const loadFileList = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    startGlobal()
    try {
      const list = await getEditFiles()
      setFiles(list)
      const fileParam = searchParams.get('file')
      const validParam = fileParam && list.some((f) => f.key === fileParam) ? fileParam : null
      setActiveKey((prev) => {
        if (validParam) return validParam
        if (prev && list.some((f) => f.key === prev)) return prev
        return list[0]?.key ?? null
      })
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Ошибка загрузки списка файлов'
      setLoadError(message)
      notifyError(message)
    } finally {
      setLoading(false)
      doneGlobal()
    }
  }, [doneGlobal, notifyError, searchParams, startGlobal])

  const loadFileContent = useCallback(
    async (key: string) => {
      setFileLoading(true)
      setFileError(null)
      try {
        const result = await getEditFileContent(key)
        setContent(result.content)
        setSavedContent(result.content)
        setDiffOpen(false)
        resetDiffBaseline()
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Ошибка чтения файла'
        setFileError(message)
        setContent('')
        setSavedContent('')
        notifyError(message)
      } finally {
        setFileLoading(false)
      }
    },
    [notifyError, resetDiffBaseline],
  )

  useEffect(() => {
    if (user?.role !== 'admin') return
    loadFileList()
  }, [user?.role, loadFileList, activeNode?.id])

  useEffect(() => {
    if (!activeKey) return
    loadFileContent(activeKey)
  }, [activeKey, loadFileContent, activeNode?.id])

  const selectFile = (key: string) => {
    if (key === activeKey) return
    if (hasUnsavedChanges) {
      confirm({
        title: 'Несохранённые изменения',
        description: 'Переключить файл без сохранения? Текущие правки будут потеряны.',
        confirmLabel: 'Переключить',
        destructive: true,
        onConfirm: () => setActiveKey(key),
      })
      return
    }
    setActiveKey(key)
  }

  const handleRefresh = async () => {
    if (hasUnsavedChanges) {
      confirm({
        title: 'Несохранённые изменения',
        description: 'Обновить данные с узла? Несохранённые правки будут потеряны.',
        confirmLabel: 'Обновить',
        destructive: true,
        onConfirm: () => void refreshFromNode(),
      })
      return
    }
    void refreshFromNode()
  }

  const refreshFromNode = async () => {
    await loadFileList()
    if (activeKey) await loadFileContent(activeKey)
    success('Данные обновлены')
  }

  const handleSaveOnly = async () => {
    if (!activeKey || !isAdmin) return
    setSaving(true)
    try {
      await withInline(
        () => saveEditFilesBatch({ [activeKey]: content }, false),
        'Сохранение файла...',
      )
      setSavedContent(content)
      resetDiffBaseline()
      success('Список сохранён на сервере')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveApply = async () => {
    if (!activeKey || !isAdmin) return
    setConfirmApply(false)
    setSaving(true)
    try {
      await withInline(() => saveEditFile(activeKey, content), 'Сохранение и doall.sh...')
      setSavedContent(content)
      resetDiffBaseline()
      success('Изменения применены — VPN обновил правила маршрутизации')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const handleRevert = () => {
    setContent(savedContent)
    resetDiffBaseline()
    success('Изменения отменены')
  }

  const handleCompareWithDisk = async () => {
    if (!activeKey || nodeOffline || fileLoading) return
    setDiskCompareLoading(true)
    try {
      const result = await getEditFileContent(activeKey)
      setDiskContent(result.content)
      setDiffBaseline('disk')
      setDiffOpen(true)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка чтения файла с узла')
    } finally {
      setDiskCompareLoading(false)
    }
  }

  const handleTransfer = async (options: {
    fileKeys: string[]
    targetNodeIds: number[] | null
    allOnline: boolean
    runDoall: boolean
    contentOverrides: Record<string, string> | null
  }) => {
    setTransferLoading(true)
    try {
      return await withInline(
        () =>
          transferEditFiles({
            file_keys: options.fileKeys,
            target_node_ids: options.targetNodeIds,
            all_online: options.allOnline,
            run_doall: options.runDoall,
            content_overrides: options.contentOverrides,
          }),
        'Перенос файлов на узлы...',
      )
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка переноса файлов')
      throw err
    } finally {
      setTransferLoading(false)
    }
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  if (loading && files.length === 0) {
    return <Spinner label="Загрузка списков..." className="py-16" />
  }

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <HaReplicaBanner />
      <PageSectionHeader
        icon={FileEdit}
        title="Редактор файлов"
        titleAddon={
          <>
            <NodeBadge name={activeNode?.name} status={activeNode?.status} />
            {hasUnsavedChanges ? (
              <Badge variant="outline" className="border-amber-500/50 text-amber-600 dark:text-amber-400">
                Несохранено
              </Badge>
            ) : null}
          </>
        }
        description={
          <>
            Списки сайтов и IP для VPN · узел{' '}
            <span className="font-medium text-foreground">{activeNode?.name ?? 'не выбран'}</span>
          </>
        }
        actions={
          <>
            {showTransferButton ? (
              <Button
                variant="outline"
                size="sm"
                className="w-full sm:w-auto"
                onClick={() => setTransferOpen(true)}
                disabled={nodeReadonly || transferLoading || files.length === 0}
              >
                <ArrowRightLeft size={15} />
                <span className="hidden sm:inline">На другие серверы</span>
                <span className="sm:hidden">На узлы</span>
              </Button>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              className="w-full sm:w-auto"
              onClick={handleRefresh}
              disabled={loading || fileLoading}
              aria-label="Обновить"
            >
              <RefreshCw size={15} className={loading || fileLoading ? 'animate-spin' : ''} />
              Обновить
            </Button>
          </>
        }
      />

      <SettingsCollapsible
        open={helpOpen}
        onOpenChange={setHelpOpen}
        title="Справка"
        description="Как править списки и что делает «Сохранить и применить»"
        icon={<HelpCircle size={16} />}
      >
        <ol className="space-y-2 text-sm text-muted-foreground">
          <li>
            <strong className="text-foreground">1.</strong> Выберите список слева — сайты, IP или рекламу.
          </li>
          <li>
            <strong className="text-foreground">2.</strong> Правьте по одной записи на строку, без запятых.
          </li>
          <li>
            <strong className="text-foreground">3.</strong> «Сохранить» — только запись на диск; «Сохранить и
            применить» — ещё и обновление маршрутов VPN (может занять несколько минут).
          </li>
        </ol>
        <p className="text-xs text-muted-foreground">
          Работа идёт на сервере «{activeNode?.name ?? 'не выбран'}». Перед правками нажмите «Обновить».
          {isHaAutoPrimary
            ? ` В группе «${activeNodeHa.group_name}» списки после сохранения копируются на резерв автоматически.`
            : null}
          {!isHaAutoPrimary && showTransferButton
            ? ` «На другие серверы» переносит списки на узлы ${ALL_NODES_ONLINE_PHRASE.toLowerCase()}.`
            : null}
        </p>
        {isHaAutoPrimary ? (
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer hover:text-foreground">HA auto — технические детали</summary>
            <p className="mt-1">
              «Сохранить» и «Сохранить и применить» реплицируют файлы на replica через config_sync.
              «Сохранить и применить» запускает doall.sh на основном узле; на реплике — при включённом
              NODE_SYNC_REPLICATE_DOALL (по умолчанию да). Кнопка копирования — запасной вариант, если
              реплика была недоступна.
            </p>
          </details>
        ) : null}
      </SettingsCollapsible>

      {nodeOffline && (
        <SettingsAlert variant="warning" title="Сервер недоступен">
          VPN-сервер не отвечает — просмотр и сохранение списков могут не работать. Проверьте связь на
          странице «Узлы».
        </SettingsAlert>
      )}

      {nodeUnknown && !nodeOffline && (
        <SettingsAlert variant="warning" title="Связь с сервером не подтверждена">
          Статус сервера неизвестен. Перед сохранением проверьте его на странице «Узлы».
        </SettingsAlert>
      )}

      {loadError && files.length === 0 ? (
        <Card>
          <CardContent>
            <EmptyState
              icon={WifiOff}
              title="Файлы недоступны"
              description={loadError}
              action={
                <Button onClick={loadFileList} disabled={loading}>
                  Обновить
                </Button>
              }
              className="py-10"
            />
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[240px_minmax(0,1fr)] lg:items-start">
          <aside className="hidden overflow-hidden rounded-lg border bg-card lg:block">
            <div className="border-b px-3 py-2">
              <p className="text-xs font-medium text-muted-foreground">Списки</p>
            </div>
            <div className="max-h-[min(70vh,40rem)] space-y-3 overflow-y-auto p-2">
              {(Object.keys(GROUP_LABELS) as FileGroup[]).map((group) => {
                const groupFiles = groupedFiles[group]
                if (groupFiles.length === 0) return null
                return (
                  <div key={group} className="space-y-0.5">
                    <div className="px-2 pb-1 pt-0.5">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                        {GROUP_LABELS[group]}
                      </p>
                    </div>
                    {groupFiles.map((f) => {
                      const meta = getFileMeta(f.key)
                      const Icon = meta.icon
                      const isActive = activeKey === f.key
                      const dirty = isActive && hasUnsavedChanges
                      return (
                        <button
                          key={f.key}
                          type="button"
                          onClick={() => selectFile(f.key)}
                          title={meta.description}
                          className={cn(
                            'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                            isActive
                              ? 'bg-primary text-primary-foreground'
                              : 'hover:bg-muted/70',
                          )}
                        >
                          <Icon
                            size={14}
                            className={cn('shrink-0', isActive ? 'opacity-90' : 'text-muted-foreground')}
                          />
                          <span className="min-w-0 flex-1 truncate font-medium">{f.title}</span>
                          {dirty ? (
                            <span
                              className={cn(
                                'h-1.5 w-1.5 shrink-0 rounded-full',
                                isActive ? 'bg-primary-foreground' : 'bg-amber-500',
                              )}
                              aria-label="Есть несохранённые правки"
                            />
                          ) : null}
                        </button>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          </aside>

          <Card className="min-w-0 shadow-sm">
            <CardHeader className="space-y-3 border-b py-3">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 space-y-0.5">
                  <CardTitle className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                    <ActiveIcon size={16} className="shrink-0 text-muted-foreground" />
                    {active?.title ?? 'Редактор'}
                    {hasUnsavedChanges ? (
                      <Badge variant="secondary" className="text-[10px]">
                        изменено
                      </Badge>
                    ) : null}
                  </CardTitle>
                  {activeMeta ? (
                    <p className="text-xs text-muted-foreground">
                      {activeMeta.description}
                      {activeMeta.hint ? ` · ${activeMeta.hint}` : ''}
                      {active?.filename ? (
                        <>
                          {' · '}
                          <span className="font-mono">{active.filename}</span>
                        </>
                      ) : null}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  <Badge variant="outline" className="tabular-nums">
                    {stats.lines}{' '}
                    {stats.lines === 1 ? 'запись' : stats.lines < 5 ? 'записи' : 'записей'}
                  </Badge>
                  <Badge variant="outline" className="tabular-nums">
                    {formatBytes(stats.bytes)}
                  </Badge>
                </div>
              </div>

              <div className="lg:hidden">
                <Label className="mb-1.5 block text-xs text-muted-foreground">Список</Label>
                <Select value={activeKey ?? undefined} onValueChange={selectFile}>
                  <SelectTrigger className="h-9 w-full min-w-0">
                    <SelectValue placeholder="Выберите список" />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(GROUP_LABELS) as FileGroup[]).map((group) => {
                      const groupFiles = groupedFiles[group]
                      if (groupFiles.length === 0) return null
                      return (
                        <SelectGroup key={group}>
                          <SelectLabel>{GROUP_LABELS[group]}</SelectLabel>
                          {groupFiles.map((f) => {
                            const label = f.filename ? `${f.title} — ${f.filename}` : f.title
                            return (
                              <SelectItem key={f.key} value={f.key} title={label}>
                                <span className="block truncate">{f.title}</span>
                              </SelectItem>
                            )
                          })}
                        </SelectGroup>
                      )
                    })}
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>

            <CardContent className="space-y-3 p-3 sm:p-4">
              {fileLoading ? (
                <Spinner label="Загрузка списка..." className="py-16" />
              ) : fileError ? (
                <EmptyState
                  icon={WifiOff}
                  title="Не удалось загрузить список"
                  description={fileError}
                  action={
                    activeKey ? (
                      <Button variant="outline" onClick={() => loadFileContent(activeKey)}>
                        Повторить
                      </Button>
                    ) : undefined
                  }
                  className="py-10"
                />
              ) : (
                <Textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  readOnly={!isAdmin}
                  placeholder={
                    activeMeta?.placeholder ?? 'Введите значения — по одному на строку'
                  }
                  className={EDITOR_TEXTAREA_CLASS}
                  spellCheck={false}
                />
              )}

              {!fileLoading && !fileError && (
                <div className="space-y-2" aria-live="polite">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-8"
                      aria-expanded={diffOpen}
                      onClick={() => setDiffOpen((open) => !open)}
                    >
                      {diffOpen ? 'Скрыть diff' : 'Показать diff'}
                    </Button>
                    {isAdmin ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 gap-1.5"
                        onClick={() => void handleCompareWithDisk()}
                        disabled={diskCompareLoading || nodeReadonly}
                        aria-label="Сравнить с сервером"
                      >
                        {diskCompareLoading ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <GitCompare size={14} />
                        )}
                        С сервером
                      </Button>
                    ) : null}
                    <span className="text-xs text-muted-foreground">{diffSummaryText}</span>
                  </div>
                  {diffOpen ? <DiffPanel ops={activeDiff.ops} mode={activeDiff.mode} /> : null}
                </div>
              )}

              {isAdmin && !fileLoading && !fileError ? (
                <div className="sticky bottom-0 z-10 -mx-3 flex flex-col gap-2 border-t bg-card/95 px-3 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/80 sm:-mx-4 sm:flex-row sm:items-center sm:justify-between sm:px-4">
                  <p className="max-w-xl text-[11px] leading-snug text-muted-foreground">
                    <strong className="text-foreground">Сохранить</strong> — на диск без VPN.{' '}
                    <strong className="text-foreground">Применить</strong> — ещё и маршруты
                    {isHaAutoPrimary ? '; на резерв уйдёт автоматически' : ''}.
                  </p>
                  <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full sm:w-auto"
                      onClick={handleRevert}
                      disabled={!hasUnsavedChanges || saving || nodeReadonly}
                      aria-label="Отменить правки"
                    >
                      <RotateCcw size={15} />
                      Отменить
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="w-full sm:w-auto"
                      onClick={handleSaveOnly}
                      disabled={!hasUnsavedChanges || saving || nodeReadonly}
                      title="Записать на сервер без обновления VPN"
                      aria-label="Сохранить"
                    >
                      {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                      Сохранить
                    </Button>
                    <Button
                      size="sm"
                      className="w-full sm:w-auto"
                      onClick={() => setConfirmApply(true)}
                      disabled={!hasUnsavedChanges || saving || nodeReadonly}
                      title="Записать и обновить правила VPN"
                    >
                      {saving ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} />}
                      Сохранить и применить
                    </Button>
                  </div>
                </div>
              ) : null}

              {!isAdmin && user?.role === 'user' ? (
                <SettingsAlert variant="info" title="Только просмотр">
                  Редактировать списки могут только администраторы. Вы можете посмотреть текущее
                  содержимое на сервере {activeNode?.name ?? ''}.
                </SettingsAlert>
              ) : null}
            </CardContent>
          </Card>
        </div>
      )}

      <ConfirmDialog
        open={confirmApply}
        onOpenChange={(open) => {
          if (!open && !saving) setConfirmApply(false)
        }}
        title="Применить изменения к VPN?"
        description={
          <>
            Список <strong>{active?.title ?? active?.filename}</strong> будет записан на сервер{' '}
            <strong>{activeNode?.name ?? 'активный'}</strong>, затем VPN обновит правила маршрутизации.
            {liveDiffCounts.added > 0 || liveDiffCounts.removed > 0 ? (
              <>
                {' '}
                Будет добавлено {liveDiffCounts.added} и удалено {liveDiffCounts.removed} записей.
              </>
            ) : null}
          </>
        }
        alert={{
          variant: 'warning',
          title: 'Это может занять несколько минут',
          children:
            'Во время обновления правил VPN у клиентов возможны кратковременные перебои в работе.',
        }}
        confirmLabel={saving ? 'Применение...' : 'Сохранить и применить'}
        destructive
        loading={saving}
        onConfirm={handleSaveApply}
        className="max-w-2xl"
      >
        {(liveDiffCounts.added > 0 || liveDiffCounts.removed > 0) && (
          <DiffPanel ops={liveDiff.ops} mode={liveDiff.mode} compact maxLines={20} />
        )}
      </ConfirmDialog>

      <TransferFilesDialog
        open={transferOpen}
        onOpenChange={setTransferOpen}
        sourceNode={activeNode}
        nodes={nodes}
        files={files}
        activeFileKey={activeKey}
        editorContent={content}
        hasUnsavedChanges={hasUnsavedChanges}
        loading={transferLoading}
        onTransfer={handleTransfer}
      />
    </div>
  )
}
