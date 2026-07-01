import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  Ban,
  BarChart3,
  Calendar,
  CheckCircle2,
  Copy,
  Download,
  Gauge,
  KeyRound,
  Loader2,
  MoreHorizontal,
  QrCode,
  Shield,
  Trash2,
  Unlock,
  UserRound,
  Wifi,
  WifiOff,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ClientAccessPolicy, UserRole, VpnConfig } from '@/types'
import {
  buildAccessMeta,
  formatCreatedAt,
  formatBlockStatus,
  getConfigStatus,
  getDownloadFilename,
  hasAzProfiles,
  hasVpnProfiles,
  pickAzFile,
  pickPrimaryFile,
  pickVpnFile,
  type ProtocolTab,
} from '@/lib/configCardUtils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'

type ActionKey = 'download' | 'qr' | 'block' | 'unblock' | 'delete'

interface ConfigCardProps {
  config: VpnConfig
  tab: ProtocolTab
  policy?: ClientAccessPolicy
  userRole: UserRole
  filesLoading?: boolean
  loadingAction?: ActionKey | null
  selected?: boolean
  showSelect?: boolean
  onSelectChange?: (checked: boolean) => void
  onOpenDetails: () => void
  onCopyName: () => void
  onDownload: (path: string, filename: string) => void
  onQr: (path: string, filename: string) => void
  onBlock?: () => void
  onUnblock?: () => void
  onDelete?: () => void
  showQrDownloads?: boolean
  showTrafficLink?: boolean
  isOnline?: boolean | null
}

const statusIcons = {
  success: CheckCircle2,
  destructive: Ban,
  warning: AlertTriangle,
  secondary: Shield,
}

interface MetaRow {
  key: string
  icon: LucideIcon
  label: string
  value: string
  tone?: 'default' | 'warning' | 'danger' | 'success'
  wide?: boolean
}

function splitMetaText(text: string): { label: string; value: string } {
  if (text.includes(' · ')) {
    const [label, ...rest] = text.split(' · ')
    return { label, value: rest.join(' · ') }
  }
  if (text.includes(':')) {
    const [label, ...rest] = text.split(':')
    return { label: label.trim(), value: rest.join(':').trim() }
  }
  return { label: text, value: '' }
}

function metaRow(
  key: string,
  icon: LucideIcon,
  label: string,
  value: string,
  tone: MetaRow['tone'] = 'default',
  wide = false,
): MetaRow {
  return { key, icon, label, value, tone, wide }
}

function isNoiseMetaLine(
  text: string,
  tone: 'active' | 'expiring' | 'expired',
  options: { hideTraffic?: boolean; hideBlock?: boolean } = {},
): boolean {
  if (options.hideTraffic && (text.startsWith('Трафик') || text.startsWith('Лимит'))) {
    return true
  }
  if (options.hideBlock && text.startsWith('Блокировка')) {
    return true
  }
  if (tone === 'active') {
    if (text.startsWith('Блокировка: нет')) return true
    if (text.startsWith('Осталось: неизвестно')) return true
    if (text.startsWith('Отключение: не ограничено')) return true
  }
  return false
}

function formatTrafficMeta(policy: ClientAccessPolicy | undefined): MetaRow {
  if (!policy) {
    return metaRow('traffic', Gauge, 'Трафик', '—')
  }

  if (policy.traffic_limit_human) {
    let value = `${policy.traffic_consumed_human || '0 B'} / ${policy.traffic_limit_human}`
    if (policy.traffic_limit_period_label) {
      value += ` · ${policy.traffic_limit_period_label}`
    }
    if (policy.traffic_bytes_left_human) {
      value += ` · осталось ${policy.traffic_bytes_left_human}`
    }
    return metaRow(
      'traffic',
      Gauge,
      'Трафик',
      value,
      policy.traffic_limit_exceeded ? 'danger' : 'default',
    )
  }

  const consumed =
    policy.traffic_consumed_human && (policy.traffic_consumed_bytes ?? 0) > 0
      ? policy.traffic_consumed_human
      : '0 B'
  return metaRow('traffic', Gauge, 'Трафик', `${consumed} · без лимита`, 'default')
}

function formatBlockMeta(policy: ClientAccessPolicy | undefined): MetaRow {
  const block = formatBlockStatus(policy)
  return metaRow('block', Shield, 'Блокировка', block.value, block.tone)
}

function formatConnectionMeta(online: boolean | null): MetaRow {
  if (online === null) {
    return metaRow('connection', Wifi, 'Подключение', '—')
  }
  return metaRow(
    'connection',
    online ? Wifi : WifiOff,
    'Подключение',
    online ? 'онлайн' : 'офлайн',
    online ? 'success' : 'default',
  )
}

function buildCompactMeta(
  config: VpnConfig,
  tab: ProtocolTab,
  policy: ClientAccessPolicy | undefined,
  isAdmin: boolean,
  tone: 'active' | 'expiring' | 'expired',
  isOnline: boolean | null,
): MetaRow[] {
  const rows: MetaRow[] = [
    metaRow('created', Calendar, 'Создан', formatCreatedAt(config.created_at)),
  ]

  if (config.vpn_type === 'openvpn' && config.cert_expire_days != null) {
    rows.push(
      metaRow(
        'cert',
        KeyRound,
        'Сертификат',
        `${config.cert_expire_days} дн.`,
        tone === 'expired' ? 'danger' : tone === 'expiring' ? 'warning' : 'default',
      ),
    )
  }

  if (isAdmin && config.owner_username) {
    rows.push(metaRow('owner', UserRound, 'Владелец', config.owner_username))
  }

  if (isAdmin) {
    rows.push(formatTrafficMeta(policy))
  }

  rows.push(formatBlockMeta(policy))
  rows.push(formatConnectionMeta(isOnline))

  const { lines } = buildAccessMeta(config, tab, policy)
  const keyMeta = config.vpn_type === 'openvpn' ? lines.slice(1) : lines

  for (const line of keyMeta) {
    if (isNoiseMetaLine(line.text, tone, { hideTraffic: isAdmin, hideBlock: true })) continue
    const parsed = splitMetaText(line.text)
    if (!parsed.value && !parsed.label) continue
    rows.push(
      metaRow(
        line.text,
        line.text.startsWith('Трафик') || line.text.startsWith('Лимит') ? Gauge : Shield,
        parsed.label,
        parsed.value || parsed.label,
        tone === 'expired' ? 'danger' : tone === 'expiring' ? 'warning' : 'default',
      ),
    )
  }

  return rows
}

function MetaLine({ row }: { row: MetaRow }) {
  const Icon = row.icon
  return (
    <div
      className={cn(
        'flex min-w-0 items-baseline gap-1.5 text-xs leading-snug',
        row.wide && 'col-span-2',
        row.tone === 'danger' && 'text-destructive',
        row.tone === 'warning' && 'text-amber-700 dark:text-amber-300',
        row.tone === 'success' && 'text-emerald-600 dark:text-emerald-400',
      )}
    >
      <Icon size={12} className="mt-0.5 shrink-0 text-muted-foreground" />
      <span className="shrink-0 text-muted-foreground">{row.label}</span>
      <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{row.value}</span>
    </div>
  )
}

function IconActionButton({
  title,
  label,
  disabled,
  loading,
  onClick,
  destructive,
  className,
  children,
}: {
  title: string
  label?: string
  disabled?: boolean
  loading?: boolean
  onClick: () => void
  destructive?: boolean
  className?: string
  children: ReactNode
}) {
  return (
    <Button
      type="button"
      variant="outline"
      size={label ? 'sm' : 'icon'}
      className={cn(
        label ? 'h-8 gap-1.5 px-2 text-xs' : 'h-8 w-8 shrink-0',
        destructive && 'text-destructive hover:bg-destructive/10 hover:text-destructive',
        className,
      )}
      title={title}
      disabled={disabled}
      onClick={onClick}
    >
      {loading ? <Loader2 size={14} className="animate-spin shrink-0" /> : children}
      {label ? <span className="whitespace-nowrap">{label}</span> : null}
    </Button>
  )
}

function IconActionLink({
  title,
  label,
  to,
  className,
  children,
}: {
  title: string
  label: string
  to: string
  className?: string
  children: ReactNode
}) {
  return (
    <Button
      asChild
      variant="outline"
      size="sm"
      className={cn('h-8 gap-1.5 px-2 text-xs', className)}
      title={title}
    >
      <Link to={to}>
        {children}
        <span className="whitespace-nowrap">{label}</span>
      </Link>
    </Button>
  )
}

function DownloadButton({
  label,
  filename,
  disabled,
  loading,
  onClick,
  accent = 'default',
  className,
}: {
  label: string
  filename: string
  disabled?: boolean
  loading?: boolean
  onClick: () => void
  accent?: 'default' | 'amber'
  className?: string
}) {
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className={cn(
        'h-8 min-w-0 flex-1 gap-1.5 px-2 text-xs',
        accent === 'amber' && 'border-amber-500/40 text-amber-600 hover:bg-amber-500/10 dark:text-amber-400',
        className,
      )}
      title={`Скачать ${label}: ${filename}`}
      disabled={disabled}
      onClick={onClick}
    >
      {loading ? <Loader2 size={14} className="animate-spin shrink-0" /> : <Download size={14} className="shrink-0" />}
      <span className="truncate">{label}</span>
    </Button>
  )
}

export default function ConfigCard({
  config,
  tab,
  policy,
  userRole,
  filesLoading = false,
  loadingAction,
  selected = false,
  showSelect = false,
  onSelectChange,
  onOpenDetails,
  onCopyName,
  onDownload,
  onQr,
  onBlock,
  onUnblock,
  onDelete,
  showQrDownloads = true,
  showTrafficLink = false,
  isOnline = null,
}: ConfigCardProps) {
  const status = getConfigStatus(config, tab, policy)
  const StatusIcon = statusIcons[status.variant]
  const { tone } = buildAccessMeta(config, tab, policy)
  const vpnFile = pickVpnFile(config, tab)
  const azFile = pickAzFile(config, tab)
  const primaryFile = pickPrimaryFile(config, tab)
  const hasBothProfiles = Boolean(vpnFile && azFile)
  const isAdmin = userRole === 'admin'
  const canDelete = isAdmin || userRole === 'user'
  const isBlocked = policy?.is_blocked ?? false
  const metaRows = buildCompactMeta(config, tab, policy, isAdmin, tone, isOnline)
  const actionBusy = loadingAction != null

  const runFileAction = (
    file: VpnConfig['profile_files'][number] | undefined,
    fn: (path: string, filename: string) => void,
  ) => {
    if (!file) return
    fn(file.path, getDownloadFilename(config, file))
  }

  const statusBadgeVariant =
    status.variant === 'success'
      ? 'success'
      : status.variant === 'warning'
        ? 'warning'
        : status.variant === 'destructive'
          ? 'destructive'
          : 'secondary'

  return (
    <Card
      className={cn(
        'relative overflow-hidden rounded-xl border shadow-sm transition-colors hover:border-primary/30 hover:shadow-md',
        selected && showSelect && 'border-primary/40 bg-primary/5',
        tone === 'expired' && 'border-destructive/30',
        tone === 'expiring' && 'border-amber-500/30',
      )}
    >
      <div
        className={cn(
          'h-0.5 w-full',
          tone === 'expired' && 'bg-destructive/70',
          tone === 'expiring' && 'bg-amber-500/70',
          tone === 'active' && 'bg-emerald-500/50',
        )}
        aria-hidden
      />
      <CardHeader className="space-y-2 p-4 pb-2">
        <div className="flex items-start gap-2">
          {showSelect && (
            <Checkbox
              checked={selected}
              onCheckedChange={onSelectChange}
              aria-label={`Выбрать ${config.client_name}`}
              className="mt-0.5"
            />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <CardTitle className="flex min-w-0 items-center gap-1.5 text-sm font-semibold leading-tight">
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
                  <Copy size={13} />
                </button>
              </CardTitle>
              <Badge variant={statusBadgeVariant} className="shrink-0 gap-1 px-2 py-0.5 text-[11px]">
                <StatusIcon size={11} />
                {status.label}
              </Badge>
            </div>
            {config.description && (
              <CardDescription className="mt-1 line-clamp-2 text-xs leading-relaxed">
                {config.description}
              </CardDescription>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {(config.tags?.length ?? 0) > 0 &&
            config.tags!.map((tag) => (
              <Badge key={tag.id} variant="outline" className="h-5 px-1.5 text-[10px]">
                {tag.name}
              </Badge>
            ))}
          {config.ha ? (
            <Badge variant="outline" className="gap-1 px-1.5 text-[10px]">
              HA: {config.ha.shared_domain} ({config.ha.node_count})
            </Badge>
          ) : null}
          {hasVpnProfiles(config, tab) && (
            <span className="inline-flex items-center rounded-md border border-primary/25 bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
              VPN
            </span>
          )}
          {hasAzProfiles(config, tab) && (
            <span className="inline-flex items-center rounded-md border border-amber-500/35 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
              AntiZapret
            </span>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-2.5 p-4 pt-0">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
          {metaRows.map((row) => (
            <MetaLine key={row.key} row={row} />
          ))}
        </div>

        <div className="space-y-2 border-t border-border/60 pt-2.5">
          {filesLoading && !primaryFile && (
            <div className="grid grid-cols-2 gap-2">
              <div className="h-9 animate-pulse rounded-lg bg-muted" />
              <div className="h-9 animate-pulse rounded-lg bg-muted" />
            </div>
          )}

          {primaryFile && showQrDownloads && (
            <div className="grid grid-cols-2 gap-2">
              {hasBothProfiles ? (
                <>
                  <DownloadButton
                    label="VPN"
                    filename={getDownloadFilename(config, vpnFile!)}
                    disabled={actionBusy}
                    loading={loadingAction === 'download'}
                    onClick={() => runFileAction(vpnFile, onDownload)}
                  />
                  <DownloadButton
                    label="AntiZapret"
                    filename={getDownloadFilename(config, azFile!)}
                    disabled={actionBusy}
                    loading={loadingAction === 'download'}
                    accent="amber"
                    onClick={() => runFileAction(azFile, onDownload)}
                  />
                </>
              ) : (
                <DownloadButton
                  label="Скачать профиль"
                  filename={getDownloadFilename(config, primaryFile)}
                  disabled={actionBusy}
                  loading={loadingAction === 'download'}
                  className="col-span-2 w-full"
                  onClick={() => runFileAction(primaryFile, onDownload)}
                />
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              {primaryFile && showQrDownloads && (
                <>
                  {hasBothProfiles ? (
                    <>
                      <IconActionButton
                        title={`QR VPN: ${getDownloadFilename(config, vpnFile!)}`}
                        label="QR VPN"
                        disabled={actionBusy}
                        loading={loadingAction === 'qr'}
                        onClick={() => runFileAction(vpnFile, onQr)}
                      >
                        <QrCode size={14} className="shrink-0" />
                      </IconActionButton>
                      <IconActionButton
                        title={`QR AntiZapret: ${getDownloadFilename(config, azFile!)}`}
                        label="QR AZ"
                        disabled={actionBusy}
                        loading={loadingAction === 'qr'}
                        className="border-amber-500/40 text-amber-600 hover:bg-amber-500/10 dark:text-amber-400"
                        onClick={() => runFileAction(azFile, onQr)}
                      >
                        <QrCode size={14} className="shrink-0" />
                      </IconActionButton>
                    </>
                  ) : (
                    <IconActionButton
                      title={`QR: ${getDownloadFilename(config, primaryFile)}`}
                      label="QR-код"
                      disabled={actionBusy}
                      loading={loadingAction === 'qr'}
                      onClick={() => runFileAction(primaryFile, onQr)}
                    >
                      <QrCode size={14} className="shrink-0" />
                    </IconActionButton>
                  )}
                </>
              )}

              {showTrafficLink && (
                <IconActionLink
                  title="Статистика трафика"
                  label="Трафик"
                  to={`/traffic?client=${encodeURIComponent(config.client_name)}`}
                >
                  <BarChart3 size={14} className="shrink-0" />
                </IconActionLink>
              )}

              <IconActionButton title="Все действия" label="Ещё" onClick={onOpenDetails}>
                <MoreHorizontal size={14} className="shrink-0" />
              </IconActionButton>
            </div>

            {(onBlock || onUnblock || onDelete) && (
              <div className="flex flex-wrap items-center gap-1.5">
                {isAdmin && !isBlocked && onBlock && (
                  <IconActionButton
                    title="Заблокировать"
                    label="Блок"
                    disabled={actionBusy}
                    loading={loadingAction === 'block'}
                    onClick={onBlock}
                  >
                    <Ban size={14} className="shrink-0" />
                  </IconActionButton>
                )}
                {isAdmin && isBlocked && onUnblock && (
                  <IconActionButton
                    title="Разблокировать"
                    label="Разблок"
                    disabled={actionBusy}
                    loading={loadingAction === 'unblock'}
                    onClick={onUnblock}
                  >
                    <Unlock size={14} className="shrink-0" />
                  </IconActionButton>
                )}
                {canDelete && onDelete && (
                  <IconActionButton
                    title="Удалить"
                    label="Удалить"
                    destructive
                    disabled={actionBusy}
                    loading={loadingAction === 'delete'}
                    onClick={onDelete}
                  >
                    <Trash2 size={14} className="shrink-0" />
                  </IconActionButton>
                )}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
