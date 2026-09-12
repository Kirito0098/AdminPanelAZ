import { useState } from 'react'
import { Download, Loader2 } from 'lucide-react'
import { ApiError, downloadAwg2Backup } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { parseContentDispositionFilename } from '@/lib/profileDownloadName'

export default function BackupTab() {
  const { success, error: notifyError } = useNotifications()
  const { withInline } = useProgress()
  const [downloading, setDownloading] = useState(false)

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

  return (
    <div className="space-y-4">
      <div className="rounded-xl border bg-card/50 p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold tracking-tight">Бэкап AZ-AWG2</h2>
              <Badge variant="secondary">узкий слой</Badge>
            </div>
            <p className="max-w-2xl text-sm text-muted-foreground">
              Экспорт только данных слоя AZ-AWG2 на активном узле: клиенты, `amneziawg` и связанный
              runtime.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => void handleDownload()} disabled={downloading}>
              {downloading ? <Loader2 className="animate-spin" /> : <Download className="h-4 w-4" />}
              Скачать бэкап
            </Button>
          </div>
        </div>
      </div>

      <SettingsAlert variant="warning" title="Не замена полному backup">
        Это узкий backup слоя AZ-AWG2. Он не заменяет штатный `awg-backup`, общий backup AntiZapret или
        backup самой панели. Полная HA-синхронизация (Push full) копирует overlay AWG2, если слой
        установлен на primary. Restore overlay выполняйте через Настройки → Бэкапы, если архив панели
        содержит компонент AWG2. OpenVPN, системные env и прочие данные вне AWG2 сюда не входят.
      </SettingsAlert>

      <SettingsAlert variant="info" title="Когда использовать">
        Скачайте overlay для архива или переноса. Для отката используйте backup панели.
      </SettingsAlert>
    </div>
  )
}
