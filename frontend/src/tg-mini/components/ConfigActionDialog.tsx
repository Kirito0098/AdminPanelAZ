import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  FileKey,
  Link2,
  Loader2,
  Send,
  Settings2,
  Share2,
  UserRound,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import MiniPlatformPicker from '@/tg-mini/components/MiniPlatformPicker'
import MiniProfileFilePicker from '@/tg-mini/components/MiniProfileFilePicker'
import ConfigManagePanel from '@/tg-mini/components/ConfigManagePanel'
import { vpnTypeBadgeClass, vpnTypeLabel } from '@/tg-mini/lib/vpnLabels'
import { formatDateTime } from '@/lib/datetime'
import type { InstallPlatform, TgMiniConfig, TgMiniConfigFile, TgMiniQrLink } from '@/types'
import { useEffect, useState, type ReactNode } from 'react'

export type ConfigFeedback = { tone: 'success' | 'error' | 'info'; text: string }

type SheetTab = 'delivery' | 'manage'

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
  canManage: boolean
  isAdmin: boolean
  onClose: () => void
  onSend: (destination: 'self' | 'owner') => void
  onCreateDownloadLink: () => void
  onCopyDownloadLink: () => void
  onShareDownloadLink: () => void
  onOpenDownloadLink: () => void
  onConfigDeleted: () => void
  onConfigUpdated: () => void
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
        <Link2 size={18} className="shrink-0 opacity-70" aria-hidden />
      )}
      <p className="text-sm leading-snug">{feedback.text}</p>
    </div>
  )
}

function StepCard({
  step,
  title,
  children,
  className,
}: {
  step?: number
  title: string
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('tg-mini-step-card', className)}>
      <div className="tg-mini-step-card-head">
        {step != null && <span className="tg-mini-step-badge">{step}</span>}
        <h3 className="tg-mini-step-title">{title}</h3>
      </div>
      <div className="tg-mini-step-card-body">{children}</div>
    </section>
  )
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
    link.max_downloads === 1 ? 'одноразовая' : `до ${link.max_downloads} скачиваний`

  return (
    <StepCard step={3} title="Ссылка готова">
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
    </StepCard>
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
  canManage,
  isAdmin,
  onClose,
  onSend,
  onCreateDownloadLink,
  onCopyDownloadLink,
  onShareDownloadLink,
  onOpenDownloadLink,
  onConfigDeleted,
  onConfigUpdated,
}: ConfigActionDialogProps) {
  const [sentSuccess, setSentSuccess] = useState(false)
  const [activeTab, setActiveTab] = useState<SheetTab>('delivery')

  useEffect(() => {
    setSentSuccess(false)
    setActiveTab('delivery')
  }, [config?.id])

  useEffect(() => {
    if (feedback?.tone === 'success' && /telegram/i.test(feedback.text)) {
      setSentSuccess(true)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
    }
  }, [feedback])

  const ownerBlocked = isForeignConfig && config?.owner_telegram_linked === false
  const canAct = files.length > 0 && Boolean(selectedPath) && !loading && !ownerBlocked
  const showDeliveryFooter = activeTab === 'delivery' && !loading

  return (
    <Dialog open={Boolean(config)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="tg-mini-dialog-sheet tg-mini-config-sheet max-w-lg gap-0 p-0 sm:rounded-t-2xl">
        <div className="tg-mini-sheet-handle" aria-hidden />

        <header className="tg-mini-config-hero">
          <div className="tg-mini-config-hero-main">
            <span className="tg-mini-config-hero-icon" aria-hidden>
              <FileKey size={20} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2 pr-6">
                <DialogTitle className="tg-mini-config-hero-title">{config?.client_name}</DialogTitle>
                {config && (
                  <span className={cn('tg-mini-protocol-badge', vpnTypeBadgeClass(config.vpn_type))}>
                    {vpnTypeLabel(config.vpn_type)}
                  </span>
                )}
              </div>
              <DialogDescription className="tg-mini-config-hero-desc">
                {sentSuccess
                  ? 'Конфиг и инструкция отправлены в Telegram'
                  : isForeignConfig
                    ? `Отправка пользователю ${ownerLabel || ''}`.trim()
                    : 'Выберите профиль и устройство — бот пришлёт файл с инструкцией'}
              </DialogDescription>
            </div>
          </div>

          {isForeignConfig && ownerLabel && !sentSuccess && (
            <div className="tg-mini-config-hero-chip">
              <UserRound size={14} aria-hidden />
              <span>{ownerLabel}</span>
            </div>
          )}
        </header>

        {canManage && !sentSuccess && (
          <div className="tg-mini-sheet-tabs" role="tablist" aria-label="Разделы конфига">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'delivery'}
              className={cn('tg-mini-sheet-tab', activeTab === 'delivery' && 'is-active')}
              onClick={() => setActiveTab('delivery')}
            >
              <Send size={16} aria-hidden />
              Получить
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'manage'}
              className={cn('tg-mini-sheet-tab', activeTab === 'manage' && 'is-active')}
              onClick={() => setActiveTab('manage')}
            >
              <Settings2 size={16} aria-hidden />
              Управление
            </button>
          </div>
        )}

        <div className="tg-mini-config-sheet-body">
          {loading ? (
            <div className="tg-mini-center py-12">
              <Loader2 size={28} className="animate-spin text-muted-foreground" aria-hidden />
              <p className="text-sm text-muted-foreground">Загрузка профилей…</p>
            </div>
          ) : sentSuccess ? (
            <div className="tg-mini-success-panel">
              <div className="tg-mini-success-icon" aria-hidden>
                <CheckCircle2 size={40} />
              </div>
              <p className="tg-mini-success-title">Готово</p>
              <p className="tg-mini-success-text">
                Проверьте чат с ботом — там файл профиля и пошаговая установка
              </p>
              {feedback && <FeedbackBanner feedback={feedback} />}
            </div>
          ) : activeTab === 'delivery' ? (
            <div className="tg-mini-config-steps">
              <StepCard step={1} title="Профиль">
                <MiniProfileFilePicker
                  files={files}
                  selectedPath={selectedPath}
                  onSelectedPathChange={onSelectedPathChange}
                />
              </StepCard>

              {files.length > 0 && !downloadLink && (
                <StepCard step={2} title={isForeignConfig ? 'Устройство пользователя' : 'Ваше устройство'}>
                  <MiniPlatformPicker
                    value={platform}
                    onChange={onPlatformChange}
                    label={isForeignConfig ? 'Устройство пользователя' : 'Ваше устройство'}
                  />
                </StepCard>
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
                  <AlertCircle size={18} className="shrink-0" aria-hidden />
                  <p className="text-sm">У владельца не привязан Telegram — отправка недоступна</p>
                </div>
              )}

              {feedback && !downloadLink && <FeedbackBanner feedback={feedback} />}
            </div>
          ) : (
            canManage &&
            config && (
              <ConfigManagePanel
                config={config}
                isAdmin={isAdmin}
                onDeleted={onConfigDeleted}
                onUpdated={onConfigUpdated}
              />
            )
          )}
        </div>

        {showDeliveryFooter && (
          <footer className="tg-mini-config-sheet-footer">
            {sentSuccess ? (
              <Button type="button" className="w-full" size="lg" onClick={onClose}>
                Закрыть
              </Button>
            ) : (
              <>
                <Button
                  type="button"
                  className="w-full gap-2"
                  size="lg"
                  disabled={!canAct || actionLoading}
                  onClick={() => onSend(isForeignConfig ? 'owner' : 'self')}
                >
                  {actionLoading ? (
                    <Loader2 size={18} className="animate-spin" aria-hidden />
                  ) : (
                    <Send size={18} aria-hidden />
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
                  {downloadLink ? 'Новая ссылка' : 'Ссылка на скачивание'}
                </Button>
              </>
            )}
          </footer>
        )}

        {activeTab === 'manage' && !loading && !sentSuccess && (
          <footer className="tg-mini-config-sheet-footer tg-mini-config-sheet-footer--hint">
            <p className="text-center text-xs text-muted-foreground">
              Изменения применяются сразу на активном узле
            </p>
          </footer>
        )}
      </DialogContent>
    </Dialog>
  )
}
