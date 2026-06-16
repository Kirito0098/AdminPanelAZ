import { useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  ArrowRightLeft,
  CheckCircle2,
  FileText,
  Files,
  Loader2,
  Server,
  Zap,
} from 'lucide-react'
import { NodeStatusBadge } from '@/components/NodeSelector'
import AppDialog from '@/components/shared/AppDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { EditFileTransferResult } from '@/api/client'
import { cn } from '@/lib/utils'
import type { EditFileEntry, Node } from '@/types'

export interface TransferFilesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sourceNode: Node | null
  nodes: Node[]
  files: EditFileEntry[]
  activeFileKey: string | null
  editorContent: string
  hasUnsavedChanges: boolean
  loading: boolean
  /** По умолчанию «все файлы» — действие на уровне страницы, не отдельного файла */
  defaultTransferAllFiles?: boolean
  onTransfer: (options: {
    fileKeys: string[]
    targetNodeIds: number[] | null
    allOnline: boolean
    runDoall: boolean
    contentOverrides: Record<string, string> | null
  }) => Promise<EditFileTransferResult>
}

function SectionTitle({ step, title }: { step: number; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
        {step}
      </span>
      <h3 className="text-sm font-semibold">{title}</h3>
    </div>
  )
}

function NodeCard({
  node,
  selected,
  disabled,
  onToggle,
}: {
  node: Node
  selected: boolean
  disabled?: boolean
  onToggle: (checked: boolean) => void
}) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors',
        disabled && 'cursor-not-allowed opacity-60',
        selected && !disabled
          ? 'border-primary/50 bg-primary/5 ring-1 ring-primary/20'
          : 'hover:bg-accent/50',
      )}
    >
      <input
        type="checkbox"
        checked={selected}
        disabled={disabled}
        onChange={(e) => onToggle(e.target.checked)}
        className="h-4 w-4 shrink-0 rounded border"
      />
      <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Server size={14} className="shrink-0 text-muted-foreground" />
            <span className="truncate text-sm font-medium">{node.name}</span>
            {node.is_local && (
              <Badge variant="outline" className="h-4 px-1 text-[10px]">
                local
              </Badge>
            )}
          </div>
        </div>
        <NodeStatusBadge status={node.status} />
      </div>
    </label>
  )
}

export default function TransferFilesDialog({
  open,
  onOpenChange,
  sourceNode,
  nodes,
  files,
  activeFileKey,
  editorContent,
  hasUnsavedChanges,
  loading,
  defaultTransferAllFiles = true,
  onTransfer,
}: TransferFilesDialogProps) {
  const [allOnline, setAllOnline] = useState(false)
  const [targetNodeIds, setTargetNodeIds] = useState<number[]>([])
  const [runDoall, setRunDoall] = useState(false)
  const [transferAllFiles, setTransferAllFiles] = useState(false)
  const [useEditorContent, setUseEditorContent] = useState(false)
  const [result, setResult] = useState<EditFileTransferResult | null>(null)

  const activeFile = useMemo(
    () => files.find((file) => file.key === activeFileKey) ?? null,
    [activeFileKey, files],
  )

  const targetCandidates = useMemo(
    () => nodes.filter((node) => node.id !== sourceNode?.id),
    [nodes, sourceNode?.id],
  )
  const onlineTargets = useMemo(
    () => targetCandidates.filter((node) => node.status === 'online'),
    [targetCandidates],
  )

  const selectedFileKeys = transferAllFiles
    ? files.map((file) => file.key)
    : activeFileKey
      ? [activeFileKey]
      : []

  const targetCount = allOnline ? onlineTargets.length : targetNodeIds.length

  const canSubmit =
    selectedFileKeys.length > 0 &&
    (allOnline ? onlineTargets.length > 0 : targetNodeIds.length > 0)

  const summaryText = useMemo(() => {
    if (!canSubmit) return null
    const fileWord =
      selectedFileKeys.length === 1
        ? '1 файл'
        : `${selectedFileKeys.length} файла`
    const nodeWord = targetCount === 1 ? '1 узел' : `${targetCount} узлов`
    return `${fileWord} → ${nodeWord}`
  }, [canSubmit, selectedFileKeys.length, targetCount])

  useEffect(() => {
    if (!open) {
      setResult(null)
      setAllOnline(false)
      setTargetNodeIds([])
      setRunDoall(false)
      setTransferAllFiles(false)
      setUseEditorContent(false)
      return
    }

    setTransferAllFiles(defaultTransferAllFiles)
    if (onlineTargets.length === 1) {
      setTargetNodeIds([onlineTargets[0].id])
    }
  }, [open, onlineTargets, defaultTransferAllFiles])

  const toggleNode = (nodeId: number, checked: boolean) => {
    if (checked) {
      setTargetNodeIds([...new Set([...targetNodeIds, nodeId])])
      setAllOnline(false)
    } else {
      setTargetNodeIds(targetNodeIds.filter((id) => id !== nodeId))
    }
  }

  const handleAllOnlineChange = (checked: boolean) => {
    setAllOnline(checked)
    if (checked) {
      setTargetNodeIds([])
    } else if (onlineTargets.length === 1) {
      setTargetNodeIds([onlineTargets[0].id])
    }
  }

  const selectAllOnlineNodes = () => {
    setAllOnline(false)
    setTargetNodeIds(onlineTargets.map((node) => node.id))
  }

  const handleTransfer = async () => {
    if (!canSubmit || loading) return

    const contentOverrides =
      useEditorContent && activeFileKey && hasUnsavedChanges
        ? { [activeFileKey]: editorContent }
        : null

    try {
      const transferResult = await onTransfer({
        fileKeys: selectedFileKeys,
        targetNodeIds: allOnline ? null : targetNodeIds,
        allOnline,
        runDoall,
        contentOverrides,
      })
      setResult(transferResult)
    } catch {
      // Parent shows toast; keep dialog open for retry.
    }
  }

  const handleClose = () => {
    if (loading) return
    onOpenChange(false)
  }

  return (
    <AppDialog
      open={open}
      onOpenChange={(next) => {
        if (!next && loading) return
        onOpenChange(next)
      }}
      title="Перенести файлы на другие узлы"
      description="Копирование конфигурации AntiZapret. Исходный узел не изменяется."
      icon={ArrowRightLeft}
      className="max-w-xl"
      footer={
        result ? (
          <Button type="button" onClick={handleClose}>
            <CheckCircle2 size={16} className="mr-1.5" />
            Готово
          </Button>
        ) : (
          <>
            <Button type="button" variant="outline" onClick={handleClose} disabled={loading}>
              Отмена
            </Button>
            <Button type="button" onClick={() => void handleTransfer()} disabled={!canSubmit || loading}>
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Перенос...
                </>
              ) : (
                <>
                  <ArrowRightLeft size={16} />
                  {summaryText ? `Перенести · ${summaryText}` : 'Перенести'}
                </>
              )}
            </Button>
          </>
        )
      }
    >
      {!result ? (
        <div className="space-y-5">
          <div className="flex items-center gap-3 rounded-lg border bg-muted/30 p-3">
            <div className="flex min-w-0 flex-1 items-center gap-2 rounded-md border bg-background px-3 py-2">
              <Server size={16} className="shrink-0 text-primary" />
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{sourceNode?.name ?? 'Источник'}</div>
                <div className="text-xs text-muted-foreground">Исходный узел</div>
              </div>
              {sourceNode && <NodeStatusBadge status={sourceNode.status} showLabel={false} />}
            </div>

            <ArrowRight size={18} className="shrink-0 text-muted-foreground" />

            <div className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-dashed bg-background px-3 py-2">
              <Server size={16} className="shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">
                  {targetCount > 0
                    ? allOnline
                      ? `Все online (${onlineTargets.length})`
                      : `${targetCount} выбрано`
                    : 'Выберите узлы'}
                </div>
                <div className="text-xs text-muted-foreground">Целевые узлы</div>
              </div>
            </div>
          </div>

          <section className="space-y-3">
            <SectionTitle step={1} title="Что переносим" />
            <div className="grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setTransferAllFiles(true)}
                className={cn(
                  'rounded-lg border p-3 text-left transition-colors',
                  transferAllFiles
                    ? 'border-primary/50 bg-primary/5 ring-1 ring-primary/20'
                    : 'hover:bg-accent/50',
                )}
              >
                <div className="flex items-start gap-2">
                  <Files size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
                  <div>
                    <div className="text-sm font-medium">Все файлы</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {files.length} конфигурационных файлов с узла
                    </div>
                  </div>
                </div>
              </button>

              <button
                type="button"
                onClick={() => setTransferAllFiles(false)}
                disabled={!activeFileKey}
                className={cn(
                  'rounded-lg border p-3 text-left transition-colors',
                  !transferAllFiles
                    ? 'border-primary/50 bg-primary/5 ring-1 ring-primary/20'
                    : 'hover:bg-accent/50',
                  !activeFileKey && 'cursor-not-allowed opacity-60',
                )}
              >
                <div className="flex items-start gap-2">
                  <FileText size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium">Только открытый файл</div>
                    <div className="mt-0.5 truncate text-xs text-muted-foreground">
                      {activeFile?.title ?? 'Не выбран'}
                    </div>
                    {activeFile && (
                      <div className="mt-1 truncate font-mono text-[10px] text-muted-foreground/80">
                        {activeFile.filename}
                      </div>
                    )}
                  </div>
                </div>
              </button>
            </div>

            {hasUnsavedChanges && transferAllFiles && (
              <SettingsAlert variant="warning" title="Несохранённые правки не войдут в перенос">
                Текущий файл «{activeFile?.title}» изменён, но не сохранён на узле. При переносе всех
                файлов используются версии с диска. Сохраните файл или выберите «Только открытый файл».
              </SettingsAlert>
            )}

            {hasUnsavedChanges && activeFileKey && !transferAllFiles && (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2.5">
                <div className="min-w-0">
                  <Label htmlFor="transfer-editor-content" className="cursor-pointer text-sm font-medium">
                    Несохранённые правки
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Перенести текст из редактора, а не версию с диска узла
                  </p>
                </div>
                <Switch
                  id="transfer-editor-content"
                  checked={useEditorContent}
                  onCheckedChange={setUseEditorContent}
                />
              </div>
            )}
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <SectionTitle step={2} title="Куда переносим" />
              {!allOnline && onlineTargets.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={selectAllOnlineNodes}
                >
                  Выбрать все online
                </Button>
              )}
            </div>

            {targetCandidates.length === 0 ? (
              <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                Нет других узлов для переноса. Добавьте узел на странице «Узлы».
              </div>
            ) : (
              <div className="space-y-2">
                <label
                  className={cn(
                    'flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors',
                    allOnline
                      ? 'border-primary/50 bg-primary/5 ring-1 ring-primary/20'
                      : 'hover:bg-accent/50',
                    onlineTargets.length === 0 && 'cursor-not-allowed opacity-60',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={allOnline}
                    disabled={onlineTargets.length === 0}
                    onChange={(e) => handleAllOnlineChange(e.target.checked)}
                    className="h-4 w-4 rounded border"
                  />
                  <div className="flex flex-1 items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium">Все online-узлы</div>
                      <div className="text-xs text-muted-foreground">
                        {onlineTargets.length} доступно для переноса
                      </div>
                    </div>
                    <Badge variant="secondary" className="font-mono tabular-nums">
                      {onlineTargets.length}
                    </Badge>
                  </div>
                </label>

                {!allOnline && (
                  <div className="space-y-2 pl-1">
                    {targetCandidates.map((node) => (
                      <NodeCard
                        key={node.id}
                        node={node}
                        selected={targetNodeIds.includes(node.id)}
                        disabled={node.status !== 'online'}
                        onToggle={(checked) => toggleNode(node.id, checked)}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <SectionTitle step={3} title="После записи" />
            <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
              <div className="flex min-w-0 items-start gap-2">
                <Zap size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
                <div>
                  <Label htmlFor="transfer-run-doall" className="cursor-pointer text-sm font-medium">
                    Применить правила (doall.sh)
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    На каждом целевом узле после записи файлов
                  </p>
                </div>
              </div>
              <Switch id="transfer-run-doall" checked={runDoall} onCheckedChange={setRunDoall} />
            </div>

            {runDoall && (
              <SettingsAlert variant="warning" title="Длительная операция">
                doall.sh перезагрузит правила маршрутизации VPN — операция может занять несколько
                минут на каждом узле.
              </SettingsAlert>
            )}
          </section>

          {!canSubmit && (
            <p className="text-center text-xs text-muted-foreground">
              Выберите файлы и хотя бы один online-узел для переноса
            </p>
          )}

          {loading && (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed py-4 text-sm text-muted-foreground">
              <Loader2 size={16} className="animate-spin" />
              Перенос файлов на выбранные узлы...
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <SettingsAlert variant={result.success ? 'info' : 'warning'} title={result.message}>
            С <strong>{result.source_node_name}</strong> скопировано{' '}
            <strong>{result.files.length}</strong> файл(ов). Успешно: {result.nodes_success}, ошибок:{' '}
            {result.nodes_failed}, пропущено: {result.nodes_skipped}.
          </SettingsAlert>

          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-lg border p-3">
              <div className="text-2xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
                {result.nodes_success}
              </div>
              <div className="text-xs text-muted-foreground">Успешно</div>
            </div>
            <div className="rounded-lg border p-3">
              <div className="text-2xl font-bold tabular-nums text-red-600 dark:text-red-400">
                {result.nodes_failed}
              </div>
              <div className="text-xs text-muted-foreground">Ошибок</div>
            </div>
            <div className="rounded-lg border p-3">
              <div className="text-2xl font-bold tabular-nums">{result.nodes_skipped}</div>
              <div className="text-xs text-muted-foreground">Пропущено</div>
            </div>
          </div>

          {result.per_node.length > 0 && (
            <div className="overflow-hidden rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Узел</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead className="text-right">Файлов</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.per_node.map((entry) => (
                    <TableRow key={`${entry.node_id}-${entry.status}`}>
                      <TableCell className="text-sm">
                        {entry.node_name ?? `Узел #${entry.node_id}`}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            entry.status === 'success'
                              ? 'default'
                              : entry.status === 'failed'
                                ? 'destructive'
                                : 'secondary'
                          }
                        >
                          {entry.status === 'success'
                            ? 'Успех'
                            : entry.status === 'failed'
                              ? 'Ошибка'
                              : 'Пропущен'}
                        </Badge>
                        {entry.error && (
                          <p className="mt-1 text-xs text-muted-foreground">{entry.error}</p>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm">
                        {entry.transferred_files?.length ?? 0}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}
    </AppDialog>
  )
}
