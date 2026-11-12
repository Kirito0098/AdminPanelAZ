import { Copy, FileKey } from 'lucide-react'
import type { QrContentMode } from '@/api/http'
import { useNotifications } from '@/context/NotificationContext'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

type QrPreviewDialogProps = {
  url?: string
  filename?: string
  contentMode?: QrContentMode
  downloadUrl?: string
  onClose: () => void
}

/** Preview of a generated profile QR code; closing it is delegated to the caller (blob cleanup). */
export default function QrPreviewDialog({
  url,
  filename,
  contentMode,
  downloadUrl,
  onClose,
}: QrPreviewDialogProps) {
  const { success, error: notifyError } = useNotifications()

  const copyDownloadUrl = async () => {
    if (!downloadUrl) return
    try {
      await navigator.clipboard.writeText(downloadUrl)
      success('Ссылка скопирована в буфер')
    } catch {
      notifyError('Не удалось скопировать ссылку')
    }
  }

  return (
    <Dialog
      open={Boolean(url)}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileKey size={18} />
            {contentMode === 'download-link' ? 'QR: ссылка для скачивания' : 'QR-код профиля'}
          </DialogTitle>
          <DialogDescription>
            {filename}
            {contentMode === 'download-link' ? (
              <span className="mt-1 block text-xs text-muted-foreground">
                Профиль не помещается в один QR (типично для AntiZapret WG/AWG и OpenVPN). Отсканируйте
                камерой телефона — откроется ссылка для скачивания файла, не импорт в VPN-приложение.
              </span>
            ) : (
              <span className="mt-1 block text-xs text-muted-foreground">
                Отсканируйте VPN-приложением для импорта профиля.
              </span>
            )}
          </DialogDescription>
        </DialogHeader>
        {url && (
          <div className="flex justify-center rounded-lg border bg-muted/30 p-6">
            <img src={url} alt="QR-код конфигурации" className="max-h-72 rounded-md" />
          </div>
        )}
        {downloadUrl && (
          <DialogFooter className="sm:justify-center">
            <Button type="button" variant="outline" onClick={() => void copyDownloadUrl()}>
              <Copy size={14} />
              Скопировать ссылку
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
