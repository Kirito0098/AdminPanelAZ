import { FormEvent, useState } from 'react'
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Download,
  Gauge,
  Link2,
  Loader2,
  QrCode,
  RefreshCw,
  Shield,
  Trash2,
  Unlock,
  Zap,
} from 'lucide-react'
import {
  ApiError,
  createOneTimeLink,
  deleteConfig,
  openvpnClearTrafficLimit,
  openvpnDisconnect,
  openvpnPermanentBlock,
  openvpnSetTrafficLimit,
  openvpnTempBlock,
  openvpnUnblock,
  setConfigTags,
  updateConfig,
  wgClearTrafficLimit,
  wgPermanentBlock,
  wgSetTrafficLimit,
  wgSetExpiry,
  wgTempBlock,
  wgUnblock,
} from '@/api/client'
import ConfigOwnerSelect from '@/components/dashboard/ConfigOwnerSelect'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  getConfigStatus,
  getDownloadFilename,
  getProtocolBadgeVariant,
  hasAzProfiles,
  hasVpnProfiles,
  pickAzFile,
  pickVpnFile,
  protocolLabel,
  type ProtocolTab,
} from '@/lib/configCardUtils'
import { cn } from '@/lib/utils'
import { useNode } from '@/context/NodeContext'
import type { ClientAccessPolicy, ConfigTag, User, UserRole, VpnConfig } from '@/types'

interface ClientActionsDialogProps {
  config: VpnConfig | null
  tab: ProtocolTab
  policy?: ClientAccessPolicy
  userRole: UserRole
  ownerCandidates?: User[]
  allTags?: ConfigTag[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onRefresh: () => Promise<void>
  onQr: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onDownload: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onNotifySuccess: (msg: string) => void
  onNotifyError: (msg: string) => void
  showQrDownloads?: boolean
}

type PromptMode = 'number' | 'confirm' | 'renew' | 'expired-wg' | 'traffic-limit' | null

interface ActionItem {
  key: string
  label: string
  icon: React.ReactNode
  onClick: () => void
  hidden?: boolean
  destructive?: boolean
  title?: string
}

const statusIcons = {
  success: CheckCircle2,
  destructive: Ban,
  warning: AlertTriangle,
  secondary: Shield,
}

function ActionButton({
  action,
  busyAction,
  fullWidth = false,
  destructive = false,
}: {
  action: ActionItem
  busyAction: string | null
  fullWidth?: boolean
  destructive?: boolean
}) {
  const isBusy = busyAction === action.key
  const isDisabled = busyAction !== null

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={isDisabled}
      title={action.title ?? action.label}
      onClick={action.onClick}
      className={cn(
        'h-9 justify-start gap-2 text-left text-xs',
        fullWidth && 'col-span-2',
        destructive &&
          'border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive',
      )}
    >
      {isBusy ? <Loader2 size={14} className="shrink-0 animate-spin" /> : action.icon}
      <span className="truncate">{action.label}</span>
    </Button>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <h3 className="shrink-0 text-sm font-medium text-foreground">{children}</h3>
      <div className="h-px flex-1 bg-border" />
    </div>
  )
}

export default function ClientActionsDialog({
  config,
  tab,
  policy,
  userRole,
  ownerCandidates = [],
  allTags = [],
  open,
  onOpenChange,
  onRefresh,
  onQr,
  onDownload,
  onNotifySuccess,
  onNotifyError,
  showQrDownloads = true,
}: ClientActionsDialogProps) {
  const { activeNode } = useNode()
  const [promptMode, setPromptMode] = useState<PromptMode>(null)
  const [promptTitle, setPromptTitle] = useState('')
  const [promptMessage, setPromptMessage] = useState('')
  const [numberValue, setNumberValue] = useState('7')
  const [renewDays, setRenewDays] = useState('365')
  const [renewDate, setRenewDate] = useState('')
  const [limitValue, setLimitValue] = useState('10')
  const [limitUnit, setLimitUnit] = useState('GB')
  const [limitPeriodDays, setLimitPeriodDays] = useState('7')
  const [pendingAction, setPendingAction] = useState<((days?: number) => Promise<void>) | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)

  if (!config) return null

  const isAdmin = userRole === 'admin'
  const policyNodeName = policy?.node_name ?? activeNode?.name

  const toggleConfigTag = async (tagId: number) => {
    if (!isAdmin) return
    const current = new Set((config.tags ?? []).map((t) => t.id))
    if (current.has(tagId)) current.delete(tagId)
    else current.add(tagId)
    setBusyAction('tags')
    try {
      await setConfigTags(config.id, [...current])
      onNotifySuccess('Теги обновлены')
      await onRefresh()
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка обновления тегов')
    } finally {
      setBusyAction(null)
    }
  }

  const isOwner = userRole === 'user' || isAdmin
  const canManage = isAdmin
  const canDelete = isAdmin || userRole === 'user'
  const vpnFile = pickVpnFile(config, tab)
  const azFile = pickAzFile(config, tab)
  const isOpenVpn = config.vpn_type === 'openvpn'
  const isBlocked = policy?.is_blocked ?? false
  const blockMode = (policy?.block_mode || 'none').toLowerCase()
  const wgExpired = Boolean(policy?.expired) || blockMode === 'expired'
  const hasTrafficLimit = Boolean(policy?.traffic_limit_human || policy?.traffic_limit_bytes)
  const trafficLimitExceeded = Boolean(policy?.traffic_limit_exceeded) || blockMode === 'traffic_limit'
  const status = getConfigStatus(config, tab, policy)
  const StatusIcon = statusIcons[status.variant]

  const todayStr = () => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  }

  const runAction = async (key: string, fn: () => Promise<void>) => {
    setBusyAction(key)
    try {
      await fn()
      await onRefresh()
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка выполнения действия')
    } finally {
      setBusyAction(null)
    }
  }

  const askNumber = (title: string, message: string, defaultVal: string, action: (days: number) => Promise<void>) => {
    setPromptTitle(title)
    setPromptMessage(message)
    setNumberValue(defaultVal)
    setPendingAction(() => async (days?: number) => {
      const parsed = days ?? Number.parseInt(numberValue, 10)
      if (!Number.isFinite(parsed) || parsed < 1 || parsed > 3650) {
        onNotifyError('Значение должно быть от 1 до 3650')
        return
      }
      await action(parsed)
    })
    setPromptMode('number')
  }

  const askConfirm = (title: string, message: string, action: () => Promise<void>) => {
    setPromptTitle(title)
    setPromptMessage(message)
    setPendingAction(() => async () => {
      await action()
    })
    setPromptMode('confirm')
  }

  const handleOneTime = async (key: string, path: string) => {
    setBusyAction(key)
    try {
      const link = await createOneTimeLink(config.id, path)
      await navigator.clipboard.writeText(link.url)
      onNotifySuccess('Одноразовая ссылка скопирована в буфер')
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка формирования ссылки')
    } finally {
      setBusyAction(null)
    }
  }

  const handleFileDownload = async (key: string, path: string, filename: string) => {
    setBusyAction(key)
    try {
      await onDownload(config, path, filename)
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка скачивания')
    } finally {
      setBusyAction(null)
    }
  }

  const handleFileQr = async (key: string, path: string, filename: string) => {
    setBusyAction(key)
    try {
      await onQr(config, path, filename)
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка QR-кода')
    } finally {
      setBusyAction(null)
    }
  }

  const handleRenewCert = () => {
    const defaultDays = String(config.cert_expire_days || 365)
    setRenewDays(defaultDays)
    const days = Number.parseInt(defaultDays, 10) || 365
    const target = new Date()
    target.setDate(target.getDate() + days)
    setRenewDate(
      `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, '0')}-${String(target.getDate()).padStart(2, '0')}`,
    )
    setPromptMode('renew')
  }

  const handleOwnerChange = async (nextOwnerId: number) => {
    if (nextOwnerId === config.owner_id) return
    await runAction('change-owner', async () => {
      await updateConfig(config.id, { owner_id: nextOwnerId })
      const nextOwner = ownerCandidates.find((user) => user.id === nextOwnerId)
      onNotifySuccess(
        nextOwner
          ? `Владелец изменён на «${nextOwner.username}»`
          : 'Владелец конфигурации изменён',
      )
    })
  }

  const submitRenew = async () => {
    const days = Number.parseInt(renewDays, 10)
    if (!Number.isFinite(days) || days < 1 || days > 3650) {
      onNotifyError('Срок должен быть от 1 до 3650 дней')
      return
    }
    setPromptMode(null)
    await runAction('renew-cert', async () => {
      await updateConfig(config.id, { cert_expire_days: days })
      onNotifySuccess('Сертификат продлён')
      onOpenChange(false)
    })
  }

  const handleWgUnblock = async () => {
    if (wgExpired) {
      setPromptMode('expired-wg')
      return
    }
    await runAction('unblock', async () => {
      await wgUnblock(config.client_name)
      onNotifySuccess('Блокировка снята')
    })
  }

  const managementActions: ActionItem[] = isOpenVpn
    ? [
        {
          key: 'temp-block',
          label: 'Временная блокировка',
          icon: <Ban size={14} />,
          hidden: !canManage,
          onClick: () =>
            askNumber(
              'Временная блокировка',
              `Укажите срок блокировки для клиента «${config.client_name}»`,
              '7',
              async (days) => {
                await openvpnTempBlock(config.client_name, days)
                onNotifySuccess('Клиент временно заблокирован')
              },
            ),
        },
        {
          key: 'unblock',
          label: 'Снять блокировку',
          icon: <Unlock size={14} />,
          hidden: !canManage || !isBlocked,
          onClick: () =>
            runAction('unblock', async () => {
              await openvpnUnblock(config.client_name)
              onNotifySuccess('Блокировка снята')
            }),
        },
        {
          key: 'disconnect',
          label: 'Отключить сессию',
          icon: <Zap size={14} />,
          hidden: !canManage,
          title: 'Принудительно отключить активную сессию',
          onClick: () =>
            askConfirm(
              'Отключить клиента',
              `Принудительно отключить активную сессию «${config.client_name}» через management socket?`,
              async () => {
                await openvpnDisconnect(config.client_name)
                onNotifySuccess('Клиент отключён')
              },
            ),
        },
        {
          key: 'renew-cert',
          label: 'Продлить сертификат',
          icon: <RefreshCw size={14} />,
          hidden: !isOwner,
          onClick: handleRenewCert,
        },
        {
          key: 'traffic-limit',
          label: 'Лимит трафика',
          icon: <Gauge size={14} />,
          hidden: !canManage,
          onClick: () => {
            setLimitValue('10')
            setLimitUnit('GB')
            setLimitPeriodDays('7')
            setPromptTitle('Лимит трафика')
            setPromptMessage(`Укажите лимит для клиента «${config.client_name}»`)
            setPromptMode('traffic-limit')
          },
        },
        {
          key: 'clear-traffic-limit',
          label: 'Снять лимит трафика',
          icon: <Gauge size={14} />,
          hidden: !canManage || !hasTrafficLimit,
          onClick: () =>
            askConfirm(
              'Снять лимит трафика',
              `Снять лимит трафика для «${config.client_name}»?`,
              async () => {
                await openvpnClearTrafficLimit(config.client_name)
                onNotifySuccess('Лимит трафика снят')
              },
            ),
        },
      ]
    : [
        {
          key: 'temp-block',
          label: 'Временная блокировка',
          icon: <Ban size={14} />,
          hidden: !canManage,
          onClick: () =>
            askNumber(
              'Временная блокировка',
              `Укажите срок блокировки для клиента «${config.client_name}»`,
              '7',
              async (days) => {
                await wgTempBlock(config.client_name, days)
                onNotifySuccess('Клиент временно заблокирован')
              },
            ),
        },
        {
          key: 'unblock',
          label: 'Снять блокировку',
          icon: <Unlock size={14} />,
          hidden: !canManage || !['temp', 'permanent', 'expired'].includes(blockMode),
          onClick: handleWgUnblock,
        },
        {
          key: 'extend-expiry',
          label: 'Продлить срок',
          icon: <RefreshCw size={14} />,
          hidden: !canManage,
          onClick: () =>
            askNumber(
              'Продлить срок',
              `Укажите срок продления для клиента «${config.client_name}»`,
              '30',
              async (days) => {
                await wgSetExpiry(config.client_name, days, true)
                onNotifySuccess('Срок доступа обновлён')
              },
            ),
        },
        {
          key: 'traffic-limit',
          label: 'Лимит трафика',
          icon: <Gauge size={14} />,
          hidden: !canManage,
          onClick: () => {
            setLimitValue('10')
            setLimitUnit('GB')
            setLimitPeriodDays('7')
            setPromptTitle('Лимит трафика')
            setPromptMessage(`Укажите лимит для клиента «${config.client_name}»`)
            setPromptMode('traffic-limit')
          },
        },
        {
          key: 'clear-traffic-limit',
          label: 'Снять лимит трафика',
          icon: <Gauge size={14} />,
          hidden: !canManage || !hasTrafficLimit,
          onClick: () =>
            askConfirm(
              'Снять лимит трафика',
              `Снять лимит трафика для «${config.client_name}»?`,
              async () => {
                await wgClearTrafficLimit(config.client_name)
                onNotifySuccess('Лимит трафика снят')
              },
            ),
        },
      ]

  const dangerActions: ActionItem[] = [
    {
      key: 'permanent-block',
      label: 'Блокировать навсегда',
      icon: <Ban size={14} />,
      hidden: !canManage || isBlocked,
      destructive: true,
      onClick: () =>
        askConfirm(
          'Бессрочная блокировка',
          `Заблокировать клиента «${config.client_name}» до ручной разблокировки?`,
          async () => {
            if (isOpenVpn) {
              await openvpnPermanentBlock(config.client_name)
            } else {
              await wgPermanentBlock(config.client_name)
            }
            onNotifySuccess('Клиент заблокирован')
          },
        ),
    },
    {
      key: 'delete',
      label: 'Удалить профиль',
      icon: <Trash2 size={14} />,
      hidden: !canDelete,
      destructive: true,
      onClick: () =>
        askConfirm('Подтверждение удаления', `Удалить профиль «${config.client_name}»?`, async () => {
          await deleteConfig(config.id)
          onNotifySuccess(`Клиент «${config.client_name}» удалён`)
          onOpenChange(false)
        }),
    },
  ]

  const visibleManagement = managementActions.filter((a) => !a.hidden)
  const visibleDanger = dangerActions.filter((a) => !a.hidden)

  type FileRow = {
    key: string
    label: string
    path: string
    filename: string
  }

  const fileRows: FileRow[] = []
  if (vpnFile) {
    fileRows.push({
      key: 'vpn',
      label: isOpenVpn ? 'VPN профиль' : 'Конфигурация',
      path: vpnFile.path,
      filename: getDownloadFilename(config, vpnFile),
    })
  }
  if (azFile) {
    fileRows.push({
      key: 'az',
      label: 'AntiZapret',
      path: azFile.path,
      filename: getDownloadFilename(config, azFile),
    })
  }

  const submitPrompt = async (e?: FormEvent, daysOverride?: number) => {
    e?.preventDefault()
    if (!pendingAction) return
    setPromptMode(null)
    await runAction('prompt', async () => {
      await pendingAction(daysOverride)
    })
    setPendingAction(null)
  }

  const closePrompt = () => {
    if (busyAction !== null) return
    setPromptMode(null)
    setPendingAction(null)
  }

  const handleMainOpenChange = (next: boolean) => {
    if (!next && (busyAction !== null || promptMode !== null)) return
    onOpenChange(next)
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
    <>
      <Dialog open={open} onOpenChange={handleMainOpenChange}>
        <DialogContent className="max-h-[90vh] max-w-md gap-0 overflow-y-auto p-0 sm:max-w-md">
          <DialogHeader className="space-y-3 border-b px-6 pb-4 pt-6">
            <div className="pr-6">
              <DialogTitle className="text-xl font-semibold tracking-tight">{config.client_name}</DialogTitle>
              {config.description && (
                <DialogDescription className="mt-1 line-clamp-2">{config.description}</DialogDescription>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant={getProtocolBadgeVariant(tab)}>{protocolLabel(tab)}</Badge>
              <Badge variant={statusBadgeVariant} className="gap-1">
                <StatusIcon size={12} />
                {status.label}
              </Badge>
              {hasVpnProfiles(config, tab) && (
                <Badge variant="outline" className="text-[10px]">
                  VPN
                </Badge>
              )}
              {hasAzProfiles(config, tab) && (
                <Badge
                  variant="outline"
                  className="border-amber-500/40 text-[10px] text-amber-600 dark:text-amber-400"
                >
                  AZ
                </Badge>
              )}
              {policyNodeName && (
                <Badge variant="outline" className="text-[10px]">
                  Политика: {policyNodeName}
                </Badge>
              )}
            </div>
          </DialogHeader>

          <div className="space-y-5 px-6 py-5">
            {isAdmin && ownerCandidates.length > 0 && (
              <section className="space-y-3">
                <SectionTitle>Владелец</SectionTitle>
                <ConfigOwnerSelect
                  id={`owner-${config.id}`}
                  users={ownerCandidates}
                  value={config.owner_id}
                  onChange={(ownerId) => void handleOwnerChange(ownerId)}
                  disabled={busyAction !== null}
                  currentOwner={
                    config.owner_username
                      ? { id: config.owner_id, username: config.owner_username }
                      : undefined
                  }
                  description="Назначьте пользователя, который будет видеть этот конфиг в своём списке."
                />
              </section>
            )}

            {visibleManagement.length > 0 && (
              <section className="space-y-3">
                <SectionTitle>Управление</SectionTitle>
                <div className="grid grid-cols-2 gap-2">
                  {visibleManagement.map((action) => (
                    <ActionButton key={action.key} action={action} busyAction={busyAction} />
                  ))}
                </div>
              </section>
            )}

            {fileRows.length > 0 && showQrDownloads && (
              <section className="space-y-3">
                <SectionTitle>Файлы и доступ</SectionTitle>
                <div className="space-y-2">
                  {fileRows.map((row) => (
                    <div
                      key={row.key}
                      className="flex items-center justify-between gap-3 rounded-lg border bg-muted/20 px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{row.label}</p>
                        <p className="truncate text-[11px] text-muted-foreground">{row.filename}</p>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          title="Скачать"
                          disabled={busyAction !== null}
                          onClick={() => void handleFileDownload(`dl-${row.key}`, row.path, row.filename)}
                        >
                          {busyAction === `dl-${row.key}` ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Download size={14} />
                          )}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          title="QR-код"
                          disabled={busyAction !== null}
                          onClick={() => void handleFileQr(`qr-${row.key}`, row.path, row.filename)}
                        >
                          {busyAction === `qr-${row.key}` ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <QrCode size={14} />
                          )}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          title="Одноразовая ссылка"
                          disabled={busyAction !== null}
                          onClick={() => void handleOneTime(`link-${row.key}`, row.path)}
                        >
                          {busyAction === `link-${row.key}` ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Link2 size={14} />
                          )}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {visibleDanger.length > 0 && (
              <section className="rounded-lg border border-destructive/30 bg-destructive/5 p-3">
                <h3 className="mb-2.5 text-sm font-medium text-destructive">Опасные действия</h3>
                <div className="grid grid-cols-2 gap-2">
                  {visibleDanger.map((action) => (
                    <ActionButton
                      key={action.key}
                      action={action}
                      busyAction={busyAction}
                      destructive
                    />
                  ))}
                </div>
              </section>
            )}

            {isAdmin && allTags.length > 0 && (
              <section className="rounded-lg border p-3">
                <h3 className="mb-2.5 text-sm font-medium">Теги</h3>
                <div className="flex flex-wrap gap-2">
                  {allTags.map((tag) => {
                    const active = (config.tags ?? []).some((t) => t.id === tag.id)
                    return (
                      <Button
                        key={tag.id}
                        type="button"
                        size="sm"
                        variant={active ? 'default' : 'outline'}
                        className="h-7 text-xs"
                        disabled={busyAction === 'tags'}
                        onClick={() => void toggleConfigTag(tag.id)}
                      >
                        {tag.name}
                      </Button>
                    )
                  })}
                </div>
              </section>
            )}

            {visibleManagement.length === 0 && fileRows.length === 0 && visibleDanger.length === 0 && (
              <p className="py-4 text-center text-sm text-muted-foreground">
                Для этого клиента нет доступных действий.
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={promptMode === 'number'} onOpenChange={(v) => !v && closePrompt()}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{promptTitle}</DialogTitle>
            <DialogDescription>{promptMessage}</DialogDescription>
          </DialogHeader>
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault()
              const days = Number.parseInt(numberValue, 10)
              void submitPrompt(e, days)
            }}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="actionDays">Значение (дни, 1–3650)</Label>
              <Input
                id="actionDays"
                type="number"
                min={1}
                max={3650}
                value={numberValue}
                onChange={(e) => setNumberValue(e.target.value)}
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closePrompt} disabled={busyAction !== null}>
                Отмена
              </Button>
              <Button type="submit" disabled={busyAction !== null}>
                {busyAction === 'prompt' ? <Loader2 size={14} className="animate-spin" /> : null}
                Применить
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={promptMode === 'confirm'}
        onOpenChange={(open) => {
          if (!open) closePrompt()
        }}
        title={promptTitle}
        description={promptMessage}
        confirmLabel="Подтвердить"
        destructive
        loading={busyAction === 'prompt'}
        onConfirm={() => void submitPrompt()}
      />

      <Dialog open={promptMode === 'renew'} onOpenChange={(v) => !v && closePrompt()}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Продлить сертификат</DialogTitle>
            <DialogDescription>Укажите новый срок сертификата для клиента.</DialogDescription>
          </DialogHeader>
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault()
              void submitRenew()
            }}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="renewDays">Срок действия (дни, 1–3650)</Label>
              <Input
                id="renewDays"
                type="number"
                min={1}
                max={3650}
                value={renewDays}
                onChange={(e) => {
                  setRenewDays(e.target.value)
                  const days = Number.parseInt(e.target.value, 10)
                  if (Number.isFinite(days) && days >= 1) {
                    const target = new Date()
                    target.setDate(target.getDate() + days)
                    setRenewDate(
                      `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, '0')}-${String(target.getDate()).padStart(2, '0')}`,
                    )
                  }
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="renewDate">Дата окончания сертификата</Label>
              <Input
                id="renewDate"
                type="date"
                min={todayStr()}
                value={renewDate}
                onChange={(e) => {
                  setRenewDate(e.target.value)
                  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(e.target.value)
                  if (!match) return
                  const target = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
                  const today = new Date()
                  today.setHours(0, 0, 0, 0)
                  const diff = Math.round((target.getTime() - today.getTime()) / 86400000)
                  if (diff >= 1 && diff <= 3650) setRenewDays(String(diff))
                }}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closePrompt} disabled={busyAction !== null}>
                Отмена
              </Button>
              <Button type="submit" disabled={busyAction !== null}>
                {busyAction === 'renew-cert' ? <Loader2 size={14} className="animate-spin" /> : null}
                Сохранить
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={promptMode === 'traffic-limit'} onOpenChange={(v) => !v && closePrompt()}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{promptTitle}</DialogTitle>
            <DialogDescription>{promptMessage}</DialogDescription>
          </DialogHeader>
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault()
              const value = Number.parseFloat(limitValue)
              if (!Number.isFinite(value) || value <= 0) {
                onNotifyError('Укажите корректный лимит трафика')
                return
              }
              const period = limitPeriodDays ? Number.parseInt(limitPeriodDays, 10) : null
              if (period != null && ![1, 7, 30].includes(period)) {
                onNotifyError('Период лимита: 1, 7 или 30 дней')
                return
              }
              setPromptMode(null)
              void runAction('traffic-limit', async () => {
                if (isOpenVpn) {
                  await openvpnSetTrafficLimit(config.client_name, value, limitUnit, period)
                } else {
                  await wgSetTrafficLimit(config.client_name, value, limitUnit, period)
                }
                onNotifySuccess('Лимит трафика установлен')
              })
            }}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="limitValue">Лимит</Label>
              <div className="flex gap-2">
                <Input
                  id="limitValue"
                  type="number"
                  min={0.01}
                  step="any"
                  value={limitValue}
                  onChange={(e) => setLimitValue(e.target.value)}
                  autoFocus
                />
                <select
                  className="rounded-md border border-input bg-background px-2 text-sm"
                  value={limitUnit}
                  onChange={(e) => setLimitUnit(e.target.value)}
                >
                  <option value="MB">MB</option>
                  <option value="GB">GB</option>
                  <option value="TB">TB</option>
                </select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="limitPeriod">Период (опционально)</Label>
              <select
                id="limitPeriod"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={limitPeriodDays}
                onChange={(e) => setLimitPeriodDays(e.target.value)}
              >
                <option value="">Всё время</option>
                <option value="1">1 день (календарный)</option>
                <option value="7">7 дней (пн–вс)</option>
                <option value="30">30 дней (месяц)</option>
              </select>
            </div>
            {trafficLimitExceeded && (
              <p className="text-sm text-destructive">Клиент сейчас заблокирован по превышению лимита.</p>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closePrompt} disabled={busyAction !== null}>
                Отмена
              </Button>
              <Button type="submit" disabled={busyAction !== null}>
                {busyAction === 'traffic-limit' ? <Loader2 size={14} className="animate-spin" /> : null}
                Установить
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={promptMode === 'expired-wg'} onOpenChange={(v) => !v && closePrompt()}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Срок действия истёк</DialogTitle>
            <DialogDescription>
              Клиент «{config.client_name}» отключён по истечении срока жизни. Для разблокировки необходимо продлить
              срок.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={closePrompt} disabled={busyAction !== null}>
              Закрыть
            </Button>
            <Button
              type="button"
              disabled={busyAction !== null}
              onClick={() => {
                setPromptMode(null)
                askNumber(
                  'Продлить срок',
                  `Укажите срок продления для клиента «${config.client_name}»`,
                  '30',
                  async (days) => {
                    await wgSetExpiry(config.client_name, days, true)
                    onNotifySuccess('Срок доступа обновлён')
                  },
                )
              }}
            >
              <RefreshCw size={14} />
              Продлить срок
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
