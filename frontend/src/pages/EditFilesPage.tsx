import { useCallback, useEffect, useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Ban,
  FileEdit,
  GitCompare,
  Globe,
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
} from '@/api/client'
import DiffPanel from '@/components/edit-files/DiffPanel'
import { formatBytes } from '@/components/monitoring/MonitoringCharts'
import { NodeBadge } from '@/components/NodeSelector'
import SettingsAlert from '@/components/settings/SettingsAlert'
import ConfirmDialog, { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
  formatDiffSummary,
} from '@/lib/buildLightDiff'
import { cn } from '@/lib/utils'
import type { EditFileEntry } from '@/types'

type FileGroup = 'hosts' | 'ips' | 'adblock'

const FILE_META: Record<string, { description: string; icon: LucideIcon; group: FileGroup }> = {
  include_hosts: {
    description: 'Домены, трафик которых направляется через VPN',
    icon: Globe,
    group: 'hosts',
  },
  exclude_hosts: {
    description: 'Домены, исключённые из маршрутизации VPN',
    icon: Globe,
    group: 'hosts',
  },
  remove_hosts: {
    description: 'Домены для удаления из автоматически собранных списков',
    icon: Globe,
    group: 'hosts',
  },
  include_ips: {
    description: 'IP и CIDR для включения в маршрутизацию',
    icon: Network,
    group: 'ips',
  },
  exclude_ips: {
    description: 'IP и CIDR, исключённые из маршрутизации',
    icon: Network,
    group: 'ips',
  },
  allow_ips: {
    description: 'Разрешённые IP-адреса для доступа',
    icon: ShieldCheck,
    group: 'ips',
  },
  drop_ips: {
    description: 'IP для блокировки исходящего трафика',
    icon: ShieldBan,
    group: 'ips',
  },
  forward_ips: {
    description: 'IP для перенаправления через VPN-туннель',
    icon: Zap,
    group: 'ips',
  },
  deny_ips: {
    description: 'Запрет входящих подключений с указанных IP',
    icon: Ban,
    group: 'ips',
  },
  include_adblock_hosts: {
    description: 'Adblock — домены для включения в фильтрацию',
    icon: ShieldBan,
    group: 'adblock',
  },
  exclude_adblock_hosts: {
    description: 'Adblock — домены, исключённые из фильтрации',
    icon: ShieldCheck,
    group: 'adblock',
  },
}

const GROUP_LABELS: Record<FileGroup, string> = {
  hosts: 'Домены',
  ips: 'IP / CIDR',
  adblock: 'Adblock',
}

function lineCount(text: string) {
  if (!text) return 0
  return text.split('\n').length
}

function getFileMeta(key: string) {
  return (
    FILE_META[key] ?? {
      description: 'Конфигурационный файл AntiZapret',
      icon: FileEdit,
      group: 'hosts' as FileGroup,
    }
  )
}

export default function EditFilesPage() {
  const { user } = useAuth()
  const { activeNode } = useNode()
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

  const nodeOffline = activeNode?.status === 'offline'
  const nodeUnknown = activeNode?.status === 'unknown'
  const isAdmin = user?.role === 'admin'
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
        return 'Нет отличий от версии на узле'
      }
      return `Относительно узла: добавлено ${activeDiffCounts.added}, удалено ${activeDiffCounts.removed}`
    }
    return formatDiffSummary(liveDiffCounts)
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
      success('Файл сохранён на узле (без doall.sh)')
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
      success('Файл сохранён и применён (doall.sh)')
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

  if (user?.role === 'viewer') {
    return (
      <div className="space-y-6">
        <EmptyState
          icon={FileEdit}
          title="Редактор недоступен"
          description="Редактирование конфигурационных файлов недоступно для роли viewer."
        />
      </div>
    )
  }

  if (loading && files.length === 0) {
    return <Spinner label="Загрузка файлов..." className="py-16" />
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
                  Не сохранено
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              {files.length} конфигурационных файлов AntiZapret на активном узле
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={loading || fileLoading}>
          <RefreshCw size={16} className={loading || fileLoading ? 'animate-spin' : ''} />
          Обновить
        </Button>
      </div>

      <SettingsAlert variant="info" title="Редактирование на активном узле">
        Файлы читаются и записываются на <strong>{activeNode?.name ?? 'активном узле'}</strong>.
        Кнопка «Сохранить и применить» выполняет <strong>doall.sh</strong> и перезагружает правила
        маршрутизации VPN — используйте её после изменения списков include/exclude.
      </SettingsAlert>

      {nodeOffline && (
        <SettingsAlert variant="warning" title="Узел офлайн">
          Активный узел недоступен. Чтение и сохранение файлов может быть невозможно. Проверьте связь
          с node agent на странице «Узлы».
        </SettingsAlert>
      )}

      {nodeUnknown && !nodeOffline && (
        <SettingsAlert variant="warning" title="Статус узла неизвестен">
          Связь с узлом не подтверждена. Запустите проверку здоровья на странице «Узлы» перед
          сохранением изменений.
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
              <CardTitle className="text-sm">Конфигурационные файлы</CardTitle>
              <CardDescription>Выберите файл для редактирования</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 p-3">
              {(Object.keys(GROUP_LABELS) as FileGroup[]).map((group) => {
                const groupFiles = groupedFiles[group]
                if (groupFiles.length === 0) return null
                return (
                  <div key={group} className="space-y-1">
                    <p className="px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {GROUP_LABELS[group]}
                    </p>
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
                              <div className={cn('mt-1 font-mono text-[10px]', isActive ? 'opacity-70' : 'text-muted-foreground/70')}>
                                {f.filename}
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
                  <CardDescription className="font-mono text-xs">{active?.filename}</CardDescription>
                  {activeMeta && (
                    <p className="text-sm text-muted-foreground">{activeMeta.description}</p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline" className="gap-1 font-mono tabular-nums">
                    {stats.lines} строк
                  </Badge>
                  <Badge variant="outline" className="gap-1 font-mono tabular-nums">
                    {formatBytes(stats.bytes)}
                  </Badge>
                </div>
              </div>

              <div className="lg:hidden">
                <Select value={activeKey ?? undefined} onValueChange={selectFile}>
                  <SelectTrigger>
                    <SelectValue placeholder="Выберите файл" />
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
                <Spinner label="Загрузка содержимого..." className="py-16" />
              ) : fileError ? (
                <EmptyState
                  icon={WifiOff}
                  title="Не удалось загрузить файл"
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
                    title="Файл пуст"
                    description="Файл отсутствует на узле или не содержит строк. Вы можете добавить содержимое и сохранить."
                    className="py-8"
                  />
                  {isAdmin && (
                    <Textarea
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      placeholder="Введите содержимое файла..."
                      className="min-h-[20rem] resize-y border-zinc-800 bg-zinc-950 font-mono text-xs leading-relaxed text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-zinc-700"
                      spellCheck={false}
                    />
                  )}
                </div>
              ) : (
                <Textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  readOnly={!isAdmin}
                  className="min-h-[28rem] resize-y border-zinc-800 bg-zinc-950 font-mono text-xs leading-relaxed text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-zinc-700"
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
                      {diffOpen ? 'Скрыть diff' : 'Показать diff'}
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
                        Сравнить с диском
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
                  <p className="text-xs text-muted-foreground">
                    «Сохранить» записывает файл на узел. «Сохранить и применить» дополнительно
                    запускает doall.sh.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={handleRevert}
                      disabled={!hasUnsavedChanges || saving || nodeOffline}
                    >
                      <RotateCcw size={16} />
                      Отменить
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={handleSaveOnly}
                      disabled={!hasUnsavedChanges || saving || nodeOffline}
                    >
                      {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                      Сохранить
                    </Button>
                    <Button
                      onClick={() => setConfirmApply(true)}
                      disabled={!hasUnsavedChanges || saving || nodeOffline}
                    >
                      {saving ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
                      Сохранить и применить
                    </Button>
                  </div>
                </div>
              )}

              {!isAdmin && user?.role === 'user' && (
                <SettingsAlert variant="info" title="Только просмотр">
                  Сохранение файлов доступно только администраторам. Вы можете просматривать содержимое
                  конфигурации активного узла.
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
        title="Сохранить и применить изменения?"
        description={
          <>
            Файл <strong>{active?.filename}</strong> будет записан на узел{' '}
            <strong>{activeNode?.name ?? 'активный'}</strong>, затем выполнен doall.sh.
            {liveDiffCounts.added > 0 || liveDiffCounts.removed > 0 ? (
              <>
                {' '}
                Будет добавлено {liveDiffCounts.added} строк, удалено {liveDiffCounts.removed}.
              </>
            ) : null}
          </>
        }
        alert={{
          variant: 'warning',
          title: 'Длительная операция',
          children:
            'Это может занять несколько минут и перезагрузить правила маршрутизации VPN для всех клиентов.',
        }}
        confirmLabel={saving ? 'Применение...' : 'Сохранить и doall.sh'}
        destructive
        loading={saving}
        onConfirm={handleSaveApply}
        className="max-w-2xl"
      >
        {(liveDiffCounts.added > 0 || liveDiffCounts.removed > 0) && (
          <DiffPanel ops={liveDiff.ops} mode={liveDiff.mode} compact maxLines={20} />
        )}
      </ConfirmDialog>
    </div>
  )
}
