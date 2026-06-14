import { useCallback, useEffect, useState } from 'react'
import { Download, Eye, FileText, RefreshCw } from 'lucide-react'
import {
  ApiError,
  getRoutingResultContent,
  getRoutingResults,
} from '@/api/client'
import AppDialog from '@/components/shared/AppDialog'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { useNotifications } from '@/context/NotificationContext'
import type { RouteResultFileEntry } from '@/types'

const PUBLIC_LABELS: Record<string, string> = {
  keenetic_wg: 'Keenetic (WireGuard)',
  mikrotik_wg: 'MikroTik (WireGuard)',
  tplink_ovpn: 'TP-Link (OpenVPN)',
  route_ips: 'route-ips.txt',
}

const PUBLIC_SLUGS: Record<string, string> = {
  keenetic_wg: 'keenetic',
  mikrotik_wg: 'mikrotik',
  tplink_ovpn: 'tplink',
}

export default function RouteResultsPanel() {
  const { error: notifyError } = useNotifications()
  const [files, setFiles] = useState<RouteResultFileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [previewKey, setPreviewKey] = useState<string | null>(null)
  const [previewContent, setPreviewContent] = useState('')
  const [previewFilename, setPreviewFilename] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)

  const load = useCallback(
    async (manual = false) => {
      if (manual) setRefreshing(true)
      else setLoading(true)
      try {
        const result = await getRoutingResults()
        setFiles(result.files)
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки route-файлов')
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
    const blob = new Blob([previewContent], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = previewFilename
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return <Spinner label="Загрузка route-файлов..." className="py-8" />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Сгенерированные файлы маршрутизации на активном узле (после doall.sh)
        </p>
        <Button size="sm" variant="outline" disabled={refreshing} onClick={() => void load(true)}>
          <RefreshCw size={14} className={refreshing ? 'mr-1 animate-spin' : 'mr-1'} />
          Обновить
        </Button>
      </div>

      {files.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="Файлы не найдены"
          description="Запустите doall.sh или примените маршрутизацию, чтобы сгенерировать route-файлы"
          className="py-8"
        />
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Файл</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead className="text-right">Строк</TableHead>
                <TableHead className="text-right">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {files.map((file) => (
                <TableRow key={file.key}>
                  <TableCell>
                    <div className="font-medium">{PUBLIC_LABELS[file.key] || file.filename}</div>
                    <div className="font-mono text-xs text-muted-foreground">{file.filename}</div>
                    {PUBLIC_SLUGS[file.key] && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        Публично: /api/public/route-download/{PUBLIC_SLUGS[file.key]}
                      </div>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={file.exists ? 'default' : 'secondary'}>
                      {file.exists ? 'Готов' : 'Не сгенерирован'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {file.exists ? file.line_count : '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!file.exists}
                      onClick={() => void openPreview(file.key)}
                    >
                      <Eye size={14} className="mr-1" />
                      Просмотр
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AppDialog
        open={previewKey != null}
        onOpenChange={(open) => {
          if (!open) setPreviewKey(null)
        }}
        title={PUBLIC_LABELS[previewKey ?? ''] || previewFilename || 'Route-файл'}
        description={previewFilename ? `Файл: ${previewFilename}` : undefined}
        footer={
          <>
            <Button variant="outline" onClick={() => setPreviewKey(null)}>
              Закрыть
            </Button>
            <Button onClick={downloadPreview} disabled={!previewContent}>
              <Download size={14} className="mr-1" />
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
            className="min-h-[20rem] font-mono text-xs"
          />
        )}
      </AppDialog>
    </div>
  )
}
