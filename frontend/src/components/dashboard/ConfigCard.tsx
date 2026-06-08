import {
  AlertTriangle,
  Ban,
  Calendar,
  CheckCircle2,
  Copy,
  Download,
  Loader2,
  MoreHorizontal,
  QrCode,
  Shield,
  Trash2,
  Unlock,
} from 'lucide-react'
import type { ClientAccessPolicy, UserRole, VpnConfig } from '@/types'
import {
  buildAccessMeta,
  formatCreatedAt,
  getConfigStatus,
  getProtocolBadgeVariant,
  hasAzProfiles,
  hasVpnProfiles,
  pickPrimaryFile,
  protocolLabel,
  type ProtocolTab,
} from '@/lib/configCardUtils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

type ActionKey = 'download' | 'qr' | 'block' | 'unblock' | 'delete'

interface ConfigCardProps {
  config: VpnConfig
  tab: ProtocolTab
  policy?: ClientAccessPolicy
  userRole: UserRole
  loadingAction?: ActionKey | null
  onOpenDetails: () => void
  onCopyName: () => void
  onDownload: (path: string, filename: string) => void
  onQr: (path: string, filename: string) => void
  onBlock?: () => void
  onUnblock?: () => void
  onDelete?: () => void
  showQrDownloads?: boolean
}

const statusIcons = {
  success: CheckCircle2,
  destructive: Ban,
  warning: AlertTriangle,
  secondary: Shield,
}

export default function ConfigCard({
  config,
  tab,
  policy,
  userRole,
  loadingAction,
  onOpenDetails,
  onCopyName,
  onDownload,
  onQr,
  onBlock,
  onUnblock,
  onDelete,
  showQrDownloads = true,
}: ConfigCardProps) {
  const status = getConfigStatus(config, tab, policy)
  const StatusIcon = statusIcons[status.variant]
  const { lines, tone } = buildAccessMeta(config, tab, policy)
  const primaryFile = pickPrimaryFile(config)
  const isAdmin = userRole === 'admin'
  const canDelete = isAdmin || userRole === 'user'
  const isBlocked = policy?.is_blocked ?? false
  const showMeta = Boolean(policy) || config.vpn_type === 'openvpn'
  const keyMeta = config.vpn_type === 'openvpn' ? lines.slice(1, 3) : lines.slice(0, 2)

  const runPrimary = (action: 'download' | 'qr', fn: (path: string, filename: string) => void) => {
    if (!primaryFile) return
    fn(primaryFile.path, primaryFile.filename)
  }

  return (
    <Card
      className={cn(
        'transition-colors hover:border-primary/40 hover:shadow-md',
        tone === 'expired' && 'border-destructive/30',
        tone === 'expiring' && 'border-amber-500/30',
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield size={16} className="shrink-0 text-muted-foreground" />
              <span className="truncate">{config.client_name}</span>
              <button
                type="button"
                title="Копировать имя"
                onClick={(e) => {
                  e.stopPropagation()
                  onCopyName()
                }}
                className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-primary"
              >
                <Copy size={14} />
              </button>
            </CardTitle>
            {config.description && (
              <CardDescription className="line-clamp-2 text-xs">{config.description}</CardDescription>
            )}
          </div>
          <Badge variant={status.variant === 'success' ? 'success' : status.variant === 'warning' ? 'warning' : status.variant === 'destructive' ? 'destructive' : 'secondary'}>
            <StatusIcon size={12} />
            {status.label}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <Badge variant={getProtocolBadgeVariant(tab)}>{protocolLabel(tab)}</Badge>
          {hasVpnProfiles(config) && (
            <Badge variant="outline" className="text-[10px]">
              VPN
            </Badge>
          )}
          {hasAzProfiles(config) && (
            <Badge variant="outline" className="border-amber-500/40 text-[10px] text-amber-600 dark:text-amber-400">
              AZ
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <Calendar size={12} />
              Создан
            </p>
            <p className="text-xs">{formatCreatedAt(config.created_at)}</p>
          </div>
          {config.vpn_type === 'openvpn' && (
            <div>
              <p className="text-xs text-muted-foreground">Сертификат</p>
              <p className="text-xs">{config.cert_expire_days ?? '—'} дн.</p>
            </div>
          )}
          {showMeta &&
            keyMeta.map((line) => {
              const [label, value] = line.text.includes(':')
                ? [line.text.split(':')[0], line.text.split(':').slice(1).join(':').trim()]
                : [line.text, '']
              return (
                <div key={line.text}>
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p
                    className={cn(
                      'text-xs',
                      tone === 'expired' && 'text-destructive',
                      tone === 'expiring' && 'text-amber-600 dark:text-amber-400',
                    )}
                  >
                    {value || label}
                  </p>
                </div>
              )
            })}
        </div>

        <div className="flex flex-wrap items-center gap-1 border-t pt-3">
          {primaryFile && showQrDownloads && (
            <>
              <Button
                variant="outline"
                size="sm"
                title="Скачать профиль"
                disabled={!!loadingAction}
                onClick={() => runPrimary('download', onDownload)}
              >
                {loadingAction === 'download' ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Download size={14} />
                )}
                Скачать
              </Button>
              <Button
                variant="outline"
                size="sm"
                title="QR-код"
                disabled={!!loadingAction}
                onClick={() => runPrimary('qr', onQr)}
              >
                {loadingAction === 'qr' ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <QrCode size={14} />
                )}
                QR
              </Button>
            </>
          )}
          <Button variant="outline" size="sm" title="Все действия" onClick={onOpenDetails}>
            <MoreHorizontal size={14} />
            Ещё
          </Button>
          {isAdmin && !isBlocked && onBlock && (
            <Button
              variant="outline"
              size="sm"
              title="Заблокировать"
              disabled={!!loadingAction}
              onClick={onBlock}
            >
              {loadingAction === 'block' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Ban size={14} />
              )}
            </Button>
          )}
          {isAdmin && isBlocked && onUnblock && (
            <Button
              variant="outline"
              size="sm"
              title="Разблокировать"
              disabled={!!loadingAction}
              onClick={onUnblock}
            >
              {loadingAction === 'unblock' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Unlock size={14} />
              )}
            </Button>
          )}
          {canDelete && onDelete && (
            <Button
              variant="ghost"
              size="sm"
              title="Удалить"
              disabled={!!loadingAction}
              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={onDelete}
            >
              {loadingAction === 'delete' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Trash2 size={14} />
              )}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
