import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  FileKey,
  Loader2,
  Send,
  Share2,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import MiniPlatformPicker from '@/tg-mini/components/MiniPlatformPicker'
import MiniProfileFilePicker from '@/tg-mini/components/MiniProfileFilePicker'
import { vpnTypeLabel } from '@/tg-mini/lib/vpnLabels'
import { formatDateTime } from '@/lib/datetime'
import type { InstallPlatform, TgMiniConfig, TgMiniConfigFile, TgMiniQrLink } from '@/types'
import { useEffect, useState, type ReactNode } from 'react'

export type ConfigFeedback = { tone: 'success' | 'error' | 'info'; text: string }

interface ConfigActionDialogProps {
  config: TgMiniConfig | null
  files: TgMiniConfigFile[]
  selectedPath: string
  onSelectedPathChange: (path: string) => void
  platform: InstallPlatform
  onPlatformChange: (platform: InstallPlatform) => void
  loading: boolean
  actionLoading: boolean
  feedback: ConfigFeedback | null
  downloadLink: TgMiniQrLink | null
  canShareLink: boolean
  isForeignConfig: boolean
  ownerLabel: string | null
  onClose: () => void
  onSend: (destination: 'self' | 'owner') => void
  onCreateDownloadLink: () => void
  onCopyDownloadLink: () => void
  onShareDownloadLink: () => void
  onOpenDownloadLink: () => void
}

function FeedbackBanner({ feedback }: { feedback: ConfigFeedback }) {
  return (
    <div
      className={cn(
        'tg-mini-feedback',
        feedback.tone === 'success' && 'is-success',
        feedback.tone === 'error' && 'is-error',
        feedback.tone === 'info' && 'is-info',
      )}
      role="status"
    >
      {feedback.tone === 'success' ? (
        <CheckCircle2 size={18} className="shrink-0" aria-hidden />
      ) : feedback.tone === 'error' ? (
        <AlertCircle size={18} className="shrink-0" aria-hidden />
      ) : (
        <FileKey size={18} className="shrink-0 opacity-70" aria-hidden />
      )}
      <p className="text-sm leading-snug">{feedback.text}</p>
    </div>
  )
}

function SectionLabel({ children }: { children: ReactNode }) {
  return <p className="tg-mini-sheet-label">{children}</p>
}

function DownloadLinkPanel({
  link,
  canShare,
  isForeignConfig,
  onCopy,
  onShare,
  onOpen,
}: {
  link: TgMiniQrLink
  canShare: boolean
  isForeignConfig: boolean
  onCopy: () => void
  onShare: () => void
  onOpen: () => void
}) {
  const limit =
    link.max_downloads === 1
      ? 'одноразовая'
      : `до ${link.max_downloads} скачиваний`

  return (
    <div className="space-y-2">
      <SectionLabel>Ссылка на скачивание</SectionLabel>
      <div className="tg-mini-download-link-box">
        <p className="tg-mini-download-link-url">{link.url}</p>
        <p className="tg-mini-download-link-meta">
          {isForeignConfig
            ? 'Отправьте ссылку пользователю — откроется в браузере на его устройстве.'
            : 'Поделитесь ссылкой или откройте на нужном устройстве.'}
          {' '}
          Действует до {formatDateTime(link.expires_at)} · {limit}
          {link.pin_required ? ' · потребуется PIN' : ''}.
        </p>
        <div className="tg-mini-download-link-actions">
          {canShare && (
            <Button type="button" className="tg-mini-link-action-full gap-2" onClick={onShare}>
              <Share2 size={16} aria-hidden />
              Поделиться в Telegram
            </Button>
          )}
          <Button type="button" variant="outline" className="gap-2" onClick={onCopy}>
            <Copy size={16} aria-hidden />
            Скопировать
          </Button>
          <Button type="button" variant="outline" className="gap-2" onClick={onOpen}>
            <ExternalLink size={16} aria-hidden />
            Открыть
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function ConfigActionDialog({
  config,
  files,
  selectedPath,
  onSelectedPathChange,
  platform,
  onPlatformChange,
  loading,
  actionLoading,
  feedback,
  downloadLink,
  canShareLink,
  isForeignConfig,
  ownerLabel,
  onClose,
  onSend,
  onCreateDownloadLink,
  onCopyDownloadLink,
  onShareDownloadLink,
  onOpenDownloadLink,
}: ConfigActionDialogProps) {
  const [sentSuccess, setSentSuccess] = useState(false)

  useEffect(() => {
    setSentSuccess(false)
  }, [config?.id])

  useEffect(() => {
    if (feedback?.tone === 'success' && /telegram/i.test(feedback.text)) {
      setSentSuccess(true)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
    }
  }, [feedback])

  const ownerBlocked = isForeignConfig && config?.owner_telegram_linked === false
  const canAct = files.length > 0 && Boolean(selectedPath) && !loading && !ownerBlocked

  return (
    <Dialog open={Boolean(config)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="tg-mini-dialog-sheet max-w-lg gap-0 p-0 sm:rounded-t-2xl">
        <div className="tg-mini-sheet-handle" aria-hidden />

        <DialogHeader className="space-y-2 px-4 pb-3 pt-2 text-left">
          <div className="flex flex-wrap items-center gap-2 pr-8">
            <DialogTitle className="text-base font-semibold">{config?.client_name}</DialogTitle>
            {config && (
              <Badge variant="outline" className="font-normal">
                {vpnTypeLabel(config.vpn_type)}
              </Badge>
            )}
          </div>
          <DialogDescription className="text-xs leading-relaxed">
            {isForeignConfig
              ? `Отправка файла и инструкции пользователю ${ownerLabel || ''}`.trim()
              : 'Бот пришлёт файл профиля и пошаговую установку для выбранного устройства'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 px-4 pb-4">
          {loading ? (
            <div className="tg-mini-center py-10">
              <Loader2 size={26} className="animate-spin text-muted-foreground" aria-hidden />
              <p className="text-xs text-muted-foreground">Загрузка файлов…</p>
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <SectionLabel>Файл профиля</SectionLabel>
                <MiniProfileFilePicker
                  files={files}
                  selectedPath={selectedPath}
                  onSelectedPathChange={onSelectedPathChange}
                />
              </div>

              {files.length > 0 && !downloadLink && (
                <MiniPlatformPicker
                  value={platform}
                  onChange={onPlatformChange}
                  label={isForeignConfig ? 'Устройство пользователя' : 'Ваше устройство'}
                />
              )}

              {downloadLink && (
                <DownloadLinkPanel
                  link={downloadLink}
                  canShare={canShareLink}
                  isForeignConfig={isForeignConfig}
                  onCopy={onCopyDownloadLink}
                  onShare={onShareDownloadLink}
                  onOpen={onOpenDownloadLink}
                />
              )}

              {ownerBlocked && (
                <div className="tg-mini-feedback is-error" role="alert">
                  <p className="text-sm">У владельца не привязан Telegram — отправка недоступна</p>
                </div>
              )}

              {feedback && <FeedbackBanner feedback={feedback} />}
            </>
          )}
        </div>

        <DialogFooter className="gap-2 border-t bg-muted/20 px-4 py-4 sm:flex-col">
          {sentSuccess ? (
            <Button type="button" className="w-full" onClick={onClose}>
              Готово
            </Button>
          ) : (
            <>
              <Button
                type="button"
                className="w-full gap-2"
                disabled={!canAct || actionLoading}
                onClick={() => onSend(isForeignConfig ? 'owner' : 'self')}
              >
                {actionLoading ? (
                  <Loader2 size={16} className="animate-spin" aria-hidden />
                ) : (
                  <Send size={16} aria-hidden />
                )}
                {isForeignConfig ? 'Отправить пользователю' : 'Получить в Telegram'}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="w-full gap-2"
                disabled={!canAct || actionLoading}
                onClick={onCreateDownloadLink}
              >
                {actionLoading ? (
                  <Loader2 size={16} className="animate-spin" aria-hidden />
                ) : (
                  <Download size={16} aria-hidden />
                )}
                {downloadLink ? 'Создать новую ссылку' : 'Создать ссылку'}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
