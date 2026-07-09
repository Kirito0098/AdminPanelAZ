import { useCallback, useEffect, useState } from 'react'
import { Copy, Download, Eye, FileText, Link2, RefreshCw } from 'lucide-react'
import {
  ApiError,
  getRoutingResultContent,
  getRoutingResults,
} from '@/api/client'
import AppDialog from '@/components/shared/AppDialog'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useNotifications } from '@/context/NotificationContext'
import { publicApiUrl } from '@/lib/panelBase'
import { cn } from '@/lib/utils'
import type { RouteResultFileEntry } from '@/types'

const ROUTER_META: Record<
  string,
  { label: string; initial: string; hint: string }
> = {
  keenetic_wg: { label: 'Keenetic', initial: 'K', hint: 'WireGuard-маршруты' },
  mikrotik_wg: { label: 'MikroTik', initial: 'M', hint: 'WireGuard-маршруты' },
  tplink_ovpn: { label: 'TP-Link', initial: 'T', hint: 'OpenVPN-маршруты' },
}

const PUBLIC_SLUGS: Record<string, string> = {
  keenetic_wg: 'keenetic',
  mikrotik_wg: 'mikrotik',
  tplink_ovpn: 'tplink',
}

function buildPublicRouteUrl(key: string): string | null {
  const slug = PUBLIC_SLUGS[key]
  if (!slug) return null
  return publicApiUrl(`/public/route-download/${slug}`)
}

interface RouteResultsPanelProps {
  showPublicLinks?: boolean
}

function RouterFileRow({
  file,
  showPublicLinks,
  downloading,
  onDownload,
  onPreview,
  onCopyLink,
}: {
  file: RouteResultFileEntry
  showPublicLinks: boolean
  downloading: boolean
  onDownload: () => void
  onPreview: () => void
  onCopyLink: () => void
}) {
  const meta = ROUTER_META[file.key]
  const ready = file.exists

  return (
    <li
      className={cn(
        'rounded-xl border bg-card/50 p-3 transition-colors hover:bg-muted/30',
        !ready && 'opacity-75',
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-sm font-semibold',
              ready ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground',
            )}
          >
            {meta?.initial ?? '?'}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{meta?.label ?? file.filename}</span>
              <Badge variant={ready ? 'success' : 'secondary'} className="text-[10px]">
                {ready ? 'Готов' : 'Нет файла'}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {ready ? `${file.line_count} строк` : 'Сгенерируйте в «Маршрутизация»'}
              {meta?.hint ? ` · ${meta.hint}` : ''}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 sm:shrink-0">
          <Button size="sm" className="gap-1.5" disabled={!ready || downloading} onClick={onDownload}>
            <Download size={14} />
            {downloading ? '…' : 'Скачать'}
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" disabled={!ready} onClick={onPreview}>
            <Eye size={14} />
            Просмотр
          </Button>
          {showPublicLinks && PUBLIC_SLUGS[file.key] && (
            <Button size="sm" variant="secondary" className="gap-1.5" disabled={!ready} onClick={onCopyLink}>
              <Copy size={14} />
              Ссылка
            </Button>
          )}
        </div>
      </div>
    </li>
  )
}

export default function RouteResultsPanel({ showPublicLinks = false }: RouteResultsPanelProps) {
  const { error: notifyError, success } = useNotifications()
  const [files, setFiles] = useState<RouteResultFileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [previewKey, setPreviewKey] = useState<string | null>(null)
  const [previewContent, setPreviewContent] = useState('')
  const [previewFilename, setPreviewFilename] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [downloadingKey, setDownloadingKey] = useState<string | null>(null)

  const triggerDownload = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadFile = async (key: string) => {
    setDownloadingKey(key)
    try {
      const result = await getRoutingResultContent(key)
      triggerDownload(result.content, result.filename)
      success(`Скачан: ${result.filename}`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось скачать файл')
    } finally {
      setDownloadingKey(null)
    }
  }

  const load = useCallback(
    async (manual = false) => {
      if (manual) setRefreshing(true)
      else setLoading(true)
      try {
        const result = await getRoutingResults()
        setFiles(result.files)
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить файлы маршрутов')
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [notifyError],
  )

  useEffect(() => {
    void load()
  }, [load])

  const openPreview = async (key: string) => {
    setPreviewKey(key)
    setPreviewLoading(true)
    setPreviewContent('')
    try {
      const result = await getRoutingResultContent(key)
      setPreviewContent(result.content)
      setPreviewFilename(result.filename)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки файла')
      setPreviewKey(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  const downloadPreview = () => {
    if (!previewContent || !previewFilename) return
    triggerDownload(previewContent, previewFilename)
  }

  const copyPublicLink = async (key: string) => {
    const url = buildPublicRouteUrl(key)
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      success('Ссылка скопирована — отправьте клиенту')
    } catch {
      notifyError('Не удалось скопировать ссылку')
    }
  }

  const previewPublicUrl = previewKey ? buildPublicRouteUrl(previewKey) : null
  const routerFiles = files.filter((f) => PUBLIC_SLUGS[f.key])
  const readyCount = routerFiles.filter((f) => f.exists).length

  if (loading) {
    return <Spinner label="Загрузка файлов..." className="py-6" />
  }

  return (
    <div className="mt-auto space-y-3 rounded-xl border bg-muted/20 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium">Готовые конфиги</p>
            {routerFiles.length > 0 && (
              <Badge variant={readyCount > 0 ? 'success' : 'secondary'} className="text-[10px]">
                {readyCount}/{routerFiles.length}
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {readyCount > 0
              ? 'Файлы с активного узла — скачайте или отправьте клиенту'
              : 'Появятся после маршрутизации на активном узле'}
          </p>
        </div>
        <Button size="sm" variant="outline" className="shrink-0 gap-1.5" disabled={refreshing} onClick={() => void load(true)}>
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          Обновить
        </Button>
      </div>

      {routerFiles.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-muted-foreground/20 bg-card/30 px-4 py-8 text-center">
          <FileText className="mb-2 h-8 w-8 text-muted-foreground/70" />
          <p className="text-sm font-medium">Файлы ещё не готовы</p>
          <p className="mt-1 max-w-xs text-xs text-muted-foreground">
            Сначала примените маршрутизацию в разделе «Маршрутизация»
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {routerFiles.map((file) => (
            <RouterFileRow
              key={file.key}
              file={file}
              showPublicLinks={showPublicLinks}
              downloading={downloadingKey === file.key}
              onDownload={() => void downloadFile(file.key)}
              onPreview={() => void openPreview(file.key)}
              onCopyLink={() => void copyPublicLink(file.key)}
            />
          ))}
        </ul>
      )}

      {showPublicLinks && readyCount > 0 && (
        <p className="flex items-start gap-1.5 rounded-lg border bg-card/40 px-2.5 py-2 text-xs text-muted-foreground">
          <Link2 size={12} className="mt-0.5 shrink-0" />
          «Ссылка» копирует адрес — клиент скачает файл без входа в панель.
        </p>
      )}

      <AppDialog
        open={previewKey != null}
        onOpenChange={(open) => {
          if (!open) setPreviewKey(null)
        }}
        title={ROUTER_META[previewKey ?? '']?.label || previewFilename || 'Файл маршрутов'}
        description={previewFilename ? `Файл: ${previewFilename}` : undefined}
        className="max-w-4xl w-[min(90vw,56rem)]"
        contentClassName="max-h-[85vh] overflow-y-auto"
        footer={
          <>
            <Button variant="outline" onClick={() => setPreviewKey(null)}>
              Закрыть
            </Button>
            {showPublicLinks && previewPublicUrl && previewKey && (
              <Button variant="outline" onClick={() => void copyPublicLink(previewKey)}>
                <Copy size={14} />
                Ссылка
              </Button>
            )}
            <Button onClick={downloadPreview} disabled={!previewContent} className="gap-1.5">
              <Download size={14} />
              Скачать
            </Button>
          </>
        }
      >
        {previewLoading ? (
          <Spinner label="Загрузка..." className="py-12" />
        ) : (
          <Textarea
            value={previewContent}
            readOnly
            className="min-h-[24rem] max-h-[50vh] resize-y font-mono text-xs"
          />
        )}
      </AppDialog>
    </div>
  )
}
