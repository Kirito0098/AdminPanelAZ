import { useRef, useState } from 'react'
import { Download, Loader2, Upload } from 'lucide-react'
import { ApiError, downloadAwg2Backup, restoreAwg2Backup } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { parseContentDispositionFilename } from '@/lib/profileDownloadName'

interface BackupTabProps {
  onRestored?: () => void
}

export default function BackupTab({ onRestored }: BackupTabProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const { success, error: notifyError } = useNotifications()
  const { withInline } = useProgress()
  const [downloading, setDownloading] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [lastRestoreMessage, setLastRestoreMessage] = useState<string | null>(null)

  const handleDownload = async () => {
    setDownloading(true)
    try {
      await withInline(async () => {
        const response = await downloadAwg2Backup()
        const blob = await response.blob()
        const filename =
          parseContentDispositionFilename(response.headers.get('Content-Disposition')) ||
          'az-awg2-backup.tar.gz'
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = filename
        link.click()
        URL.revokeObjectURL(url)
      }, 'Скачивание AWG2 бэкапа...')
      success('Бэкап AZ-AWG2 скачан')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка скачивания бэкапа AZ-AWG2')
    } finally {
      setDownloading(false)
    }
  }

  const handleRestore = async (file: File) => {
    setRestoring(true)
    setLastRestoreMessage(null)
    try {
      const result = await withInline(async () => restoreAwg2Backup(file), 'Восстановление AWG2 бэкапа...')
      const haErrors = result.ha?.errors ?? []
      if (haErrors.length > 0) {
        const detail = haErrors
          .map((entry) => entry.node_name || entry.error || 'replica')
          .join(', ')
        const message = `${result.message}. HA: ${detail}`
        setLastRestoreMessage(message)
        notifyError(`Файлы восстановлены, синхронизация HA с ошибками: ${detail}`)
      } else {
        setLastRestoreMessage(result.message)
        success(result.message)
      }
      onRestored?.()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка восстановления бэкапа AZ-AWG2')
    } finally {
      setRestoring(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border bg-card/50 p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold tracking-tight">Backup / Restore AZ-AWG2</h2>
              <Badge variant="secondary">narrow scope</Badge>
            </div>
            <p className="max-w-2xl text-sm text-muted-foreground">
              Экспорт и импорт только данных слоя AZ-AWG2 на активном узле: клиенты, `amneziawg`
              и связанный runtime.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => void handleDownload()} disabled={downloading || restoring}>
              {downloading ? <Loader2 className="animate-spin" /> : <Download className="h-4 w-4" />}
              Скачать backup
            </Button>
            <Button type="button" onClick={() => inputRef.current?.click()} disabled={downloading || restoring}>
              {restoring ? <Loader2 className="animate-spin" /> : <Upload className="h-4 w-4" />}
              Загрузить и восстановить
            </Button>
            <input
              ref={inputRef}
              type="file"
              accept=".tar.gz,application/gzip,application/x-gzip"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (file) void handleRestore(file)
              }}
            />
          </div>
        </div>
      </div>

      <SettingsAlert variant="warning" title="Не замена полному backup">
        Это узкий backup слоя AZ-AWG2. Он не заменяет штатный `awg-backup`, общий backup AntiZapret или
        backup самой панели. Полная HA-синхронизация (Push full) копирует overlay AWG2, если слой
        установлен на primary. Штатный backup панели тоже может включить этот слой (галочка на создании
        копии / авто-бэкап). Узкий restore здесь — если нужен только overlay, без базы панели.
        OpenVPN, системные env и прочие данные вне AWG2 сюда не входят.
      </SettingsAlert>

      <SettingsAlert variant="info" title="Когда использовать">
        Подходит для переноса и отката клиентов AmneziaWG 2.0 вместе с текущей обфускацией. После restore
        обновите страницу и при необходимости заново скачайте клиентские профили.
      </SettingsAlert>

      {lastRestoreMessage && (
        <div className="rounded-lg border bg-card/50 px-4 py-3 text-sm">
          <span className="font-medium">Последнее восстановление:</span> {lastRestoreMessage}
        </div>
      )}
    </div>
  )
}
