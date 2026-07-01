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
import { useSearchParams } from 'react-router-dom'
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
import SettingsAlert from '@/components/settings/SettingsAlert'
import ConfirmDialog, { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import {
  buildLightDiff,
  countDiffOps,
} from '@/lib/buildLightDiff'
import { ALL_NODES_ONLINE_PHRASE } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import type { EditFileEntry } from '@/types'

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

const GROUP_HINTS: Record<FileGroup, string> = {
  hosts: 'Какие сайты пускать или не пускать через VPN',
  ips: 'Отдельные адреса и диапазоны',
  adblock: 'Дополнительные правила фильтрации рекламы',
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

  const nodeOffline = activeNode?.status === 'offline'
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
    if (user?.role === 'viewer') return
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

  if (user?.role === 'viewer') {
    return (
      <div className="space-y-6">
        <EmptyState
          icon={FileEdit}
          title="Редактор недоступен"
          description="Просмотр и редактирование списков VPN недоступны для вашей роли."
        />
      </div>
    )
  }

  if (loading && files.length === 0) {
    return <Spinner label="Загрузка списков..." className="py-16" />
  }

  return (
    <div className="space-y-6">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileEdit size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold tracking-tight">Редактор файлов</h2>
              <NodeBadge name={activeNode?.name} status={activeNode?.status} />
              {hasUnsavedChanges && (
                <Badge variant="outline" className="border-amber-500/50 text-amber-600 dark:text-amber-400">
                  Есть несохранённые правки
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              Списки сайтов и IP-адресов для VPN на сервере{' '}
              <strong className="font-medium text-foreground">{activeNode?.name ?? 'не выбран'}</strong>
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {showTransferButton && (
            <div className="flex flex-col items-start gap-0.5">
              <Button
                variant="outline"
                onClick={() => setTransferOpen(true)}
                disabled={nodeOffline || transferLoading || files.length === 0}
              >
                <ArrowRightLeft size={16} />
                Скопировать на другие серверы
              </Button>
              {isHaAutoPrimary && (
                <span className="px-1 text-[10px] text-muted-foreground">Запасной вариант</span>
              )}
            </div>
          )}
          <Button variant="outline" onClick={handleRefresh} disabled={loading || fileLoading}>
            <RefreshCw size={16} className={loading || fileLoading ? 'animate-spin' : ''} />
            Обновить
          </Button>
        </div>
      </div>

      <details className="group rounded-lg border bg-card text-sm">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 font-medium [&::-webkit-details-marker]:hidden">
          <HelpCircle size={16} className="shrink-0 text-primary" />
          Как пользоваться — 3 простых шага
          <span className="ml-auto text-xs text-muted-foreground group-open:hidden">Показать</span>
        </summary>
        <div className="space-y-3 border-t px-4 py-3 text-muted-foreground">
          <ol className="space-y-2.5">
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                1
              </span>
              <span>
                <strong className="text-foreground">Выберите список</strong> слева — сайты, IP-адреса или
                блокировку рекламы.
              </span>
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                2
              </span>
              <span>
                <strong className="text-foreground">Добавьте или уберите записи</strong> — каждый сайт или
                адрес с новой строки, без запятых.
              </span>
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                3
              </span>
              <span>
                <strong className="text-foreground">Нажмите «Сохранить и применить»</strong>, чтобы VPN
                подхватил изменения. Просто «Сохранить» записывает список, но не обновляет маршруты.
              </span>
            </li>
          </ol>
          <p className="text-xs">
            Перед правками нажмите <strong className="text-foreground">Обновить</strong>, чтобы загрузить
            актуальную версию с сервера.
          </p>
        </div>
      </details>

      {isHaAutoPrimary && (
        <SettingsAlert variant="info" title="Изменения автоматически копируются на резервный сервер">
          После сохранения списки синхронизируются с резервным узлом группы «{activeNodeHa.group_name}».
          Кнопка «Скопировать на другие серверы» нужна только в особых случаях — например, если резервный
          сервер был недоступен.
          <details className="mt-2">
            <summary className="cursor-pointer text-xs hover:text-foreground">Технические подробности</summary>
            <p className="mt-1 text-xs">
              Режим HA auto: «Сохранить» и «Сохранить и применить» реплицируют файлы на replica через
              config_sync. «Сохранить и применить» запускает doall.sh на основном узле; на реплике — при
              включённом NODE_SYNC_REPLICATE_DOALL (по умолчанию да).
            </p>
          </details>
        </SettingsAlert>
      )}

      <SettingsAlert variant="info" title={`Работа идёт на сервере «${activeNode?.name ?? 'не выбран'}»`}>
        Списки читаются и сохраняются на выбранном VPN-сервере. Кнопка{' '}
        <strong>«Сохранить и применить»</strong> обновляет правила маршрутизации — это может занять
        несколько минут.
        {!isHaAutoPrimary && showTransferButton && (
          <>
            {' '}
            Кнопка <strong>«Скопировать на другие серверы»</strong> переносит списки на другие узлы
            {ALL_NODES_ONLINE_PHRASE.toLowerCase()}.
          </>
        )}
      </SettingsAlert>

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
        <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
          <Card className="hidden lg:block">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Что изменить?</CardTitle>
              <CardDescription>Выберите нужный список</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 p-3">
              {(Object.keys(GROUP_LABELS) as FileGroup[]).map((group) => {
                const groupFiles = groupedFiles[group]
                if (groupFiles.length === 0) return null
                return (
                  <div key={group} className="space-y-1">
                    <div className="px-2">
                      <p className="text-xs font-medium text-foreground">{GROUP_LABELS[group]}</p>
                      <p className="text-[11px] leading-snug text-muted-foreground">{GROUP_HINTS[group]}</p>
                    </div>
                    {groupFiles.map((f) => {
                      const meta = getFileMeta(f.key)
                      const Icon = meta.icon
                      const isActive = activeKey === f.key
                      return (
                        <button
                          key={f.key}
                          type="button"
                          onClick={() => selectFile(f.key)}
                          className={cn(
                            'w-full rounded-lg px-3 py-2.5 text-left transition-colors',
                            isActive
                              ? 'bg-primary text-primary-foreground'
                              : 'hover:bg-accent',
                          )}
                        >
                          <div className="flex items-start gap-2">
                            <Icon
                              size={14}
                              className={cn('mt-0.5 shrink-0', isActive ? 'opacity-90' : 'text-muted-foreground')}
                            />
                            <div className="min-w-0">
                              <div className="text-sm font-medium leading-tight">{f.title}</div>
                              <div
                                className={cn(
                                  'mt-0.5 text-xs leading-snug',
                                  isActive ? 'opacity-80' : 'text-muted-foreground',
                                )}
                              >
                                {meta.description}
                              </div>
                            </div>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                )
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="space-y-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 space-y-1">
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    <ActiveIcon size={18} className="shrink-0 text-muted-foreground" />
                    {active?.title ?? 'Редактор'}
                    {hasUnsavedChanges && (
                      <Badge variant="secondary" className="text-[10px]">
                        изменено
                      </Badge>
                    )}
                  </CardTitle>
                  {activeMeta && (
                    <>
                      <p className="text-sm text-foreground">{activeMeta.description}</p>
                      <p className="text-xs text-muted-foreground">{activeMeta.hint}</p>
                    </>
                  )}
                  {active?.filename && (
                    <details className="text-xs text-muted-foreground">
                      <summary className="cursor-pointer hover:text-foreground">Имя файла на сервере</summary>
                      <p className="mt-1 font-mono">{active.filename}</p>
                    </details>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline" className="gap-1 tabular-nums">
                    {stats.lines} {stats.lines === 1 ? 'запись' : stats.lines < 5 ? 'записи' : 'записей'}
                  </Badge>
                  <Badge variant="outline" className="gap-1 tabular-nums">
                    {formatBytes(stats.bytes)}
                  </Badge>
                </div>
              </div>

              <div className="lg:hidden">
                <Label className="mb-1.5 block text-xs text-muted-foreground">Какой список открыть?</Label>
                <Select value={activeKey ?? undefined} onValueChange={selectFile}>
                  <SelectTrigger>
                    <SelectValue placeholder="Выберите список" />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(GROUP_LABELS) as FileGroup[]).map((group) =>
                      groupedFiles[group].map((f) => (
                        <SelectItem key={f.key} value={f.key}>
                          {GROUP_LABELS[group]} · {f.title}
                        </SelectItem>
                      )),
                    )}
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
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
              ) : content.length === 0 ? (
                <div className="space-y-4">
                  <EmptyState
                    icon={FileEdit}
                    title="Список пока пуст"
                    description="Здесь пока нет записей. Добавьте сайты или адреса — по одному на строку — и нажмите «Сохранить и применить»."
                    className="py-8"
                  />
                  {isAdmin && (
                    <Textarea
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      placeholder={activeMeta?.placeholder ?? 'Введите значения — по одному на строку'}
                      className="min-h-[20rem] resize-y border-zinc-800 bg-zinc-950 font-mono text-sm leading-relaxed text-zinc-200 placeholder:text-zinc-500 focus-visible:ring-zinc-700"
                      spellCheck={false}
                    />
                  )}
                </div>
              ) : (
                <Textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  readOnly={!isAdmin}
                  placeholder={activeMeta?.placeholder}
                  className="min-h-[28rem] resize-y border-zinc-800 bg-zinc-950 font-mono text-sm leading-relaxed text-zinc-200 placeholder:text-zinc-500 focus-visible:ring-zinc-700"
                  spellCheck={false}
                />
              )}

              {!fileLoading && !fileError && (
                <div className="space-y-3" aria-live="polite">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      aria-expanded={diffOpen}
                      onClick={() => setDiffOpen((open) => !open)}
                    >
                      {diffOpen ? 'Скрыть изменения' : 'Показать изменения'}
                    </Button>
                    {isAdmin && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => void handleCompareWithDisk()}
                        disabled={diskCompareLoading || nodeOffline}
                      >
                        {diskCompareLoading ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : (
                          <GitCompare size={16} />
                        )}
                        Сравнить с сервером
                      </Button>
                    )}
                    <span className="text-xs text-muted-foreground">{diffSummaryText}</span>
                  </div>
                  {diffOpen && (
                    <DiffPanel ops={activeDiff.ops} mode={activeDiff.mode} />
                  )}
                </div>
              )}

              {isAdmin && !fileLoading && !fileError && (
                <div className="flex flex-col gap-3 border-t pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                  <p className="max-w-xl text-xs text-muted-foreground">
                    <strong className="text-foreground">Сохранить</strong> — записать список на сервер без
                    обновления VPN.{' '}
                    <strong className="text-foreground">Сохранить и применить</strong> — обновить правила
                    маршрутизации (может занять несколько минут).
                    {isHaAutoPrimary && ' На резервный сервер списки скопируются автоматически.'}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={handleRevert}
                      disabled={!hasUnsavedChanges || saving || nodeOffline}
                    >
                      <RotateCcw size={16} />
                      Отменить правки
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={handleSaveOnly}
                      disabled={!hasUnsavedChanges || saving || nodeOffline}
                      title="Записать на сервер без обновления VPN"
                    >
                      {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                      Сохранить
                    </Button>
                    <Button
                      onClick={() => setConfirmApply(true)}
                      disabled={!hasUnsavedChanges || saving || nodeOffline}
                      title="Записать и обновить правила VPN"
                    >
                      {saving ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
                      Сохранить и применить
                    </Button>
                  </div>
                </div>
              )}

              {!isAdmin && user?.role === 'user' && (
                <SettingsAlert variant="info" title="Только просмотр">
                  Редактировать списки могут только администраторы. Вы можете посмотреть текущее
                  содержимое на сервере {activeNode?.name ?? ''}.
                </SettingsAlert>
              )}
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
