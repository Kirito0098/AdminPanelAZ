import { FormEvent, useState } from 'react'
import {
  ApiError,
  createOneTimeLink,
  deleteConfig,
  openvpnDisconnect,
  openvpnPermanentBlock,
  openvpnTempBlock,
  openvpnUnblock,
  updateConfig,
  wgPermanentBlock,
  wgSetExpiry,
  wgTempBlock,
  wgUnblock,
} from '@/api/client'
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
import { pickAzFile, pickVpnFile, type ProtocolTab } from '@/lib/configCardUtils'
import type { ClientAccessPolicy, UserRole, VpnConfig } from '@/types'

interface ClientActionsDialogProps {
  config: VpnConfig | null
  tab: ProtocolTab
  policy?: ClientAccessPolicy
  userRole: UserRole
  open: boolean
  onOpenChange: (open: boolean) => void
  onRefresh: () => Promise<void>
  onQr: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onDownload: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onNotifySuccess: (msg: string) => void
  onNotifyError: (msg: string) => void
}

type PromptMode = 'number' | 'confirm' | 'renew' | 'expired-wg' | null

export default function ClientActionsDialog({
  config,
  tab,
  policy,
  userRole,
  open,
  onOpenChange,
  onRefresh,
  onQr,
  onDownload,
  onNotifySuccess,
  onNotifyError,
}: ClientActionsDialogProps) {
  const [promptMode, setPromptMode] = useState<PromptMode>(null)
  const [promptTitle, setPromptTitle] = useState('')
  const [promptMessage, setPromptMessage] = useState('')
  const [numberValue, setNumberValue] = useState('7')
  const [renewDays, setRenewDays] = useState('365')
  const [renewDate, setRenewDate] = useState('')
  const [pendingAction, setPendingAction] = useState<((days?: number) => Promise<void>) | null>(null)
  const [busy, setBusy] = useState(false)

  if (!config) return null

  const isAdmin = userRole === 'admin'
  const isOwner = userRole === 'user' || isAdmin
  const canManage = isAdmin
  const canDelete = isAdmin || userRole === 'user'
  const vpnFile = pickVpnFile(config)
  const azFile = pickAzFile(config)
  const isOpenVpn = config.vpn_type === 'openvpn'
  const isBlocked = policy?.is_blocked ?? false
  const blockMode = (policy?.block_mode || 'none').toLowerCase()
  const wgExpired = Boolean(policy?.expired) || blockMode === 'expired'

  const todayStr = () => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  }

  const runAction = async (fn: () => Promise<void>) => {
    setBusy(true)
    try {
      await fn()
      await onRefresh()
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка выполнения действия')
    } finally {
      setBusy(false)
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

  const handleOneTime = async (path: string) => {
    try {
      const link = await createOneTimeLink(config.id, path)
      await navigator.clipboard.writeText(link.url)
      onNotifySuccess('Одноразовая ссылка скопирована в буфер')
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка формирования ссылки')
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

  const submitRenew = async () => {
    const days = Number.parseInt(renewDays, 10)
    if (!Number.isFinite(days) || days < 1 || days > 3650) {
      onNotifyError('Срок должен быть от 1 до 3650 дней')
      return
    }
    setPromptMode(null)
    await runAction(async () => {
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
    await runAction(async () => {
      await wgUnblock(config.client_name)
      onNotifySuccess('Блокировка снята')
    })
  }

  const actionGroups: Array<{ title: string; actions: Array<{ label: string; onClick: () => void; hidden?: boolean }> }> =
    [
      {
        title: 'Управление',
        actions: [
          {
            label: '⛔ Временная блокировка OpenVPN',
            hidden: !canManage || !isOpenVpn,
            onClick: () =>
              askNumber(
                'Временная блокировка OpenVPN',
                `Укажите срок блокировки для клиента «${config.client_name}»`,
                '7',
                async (days) => {
                  await openvpnTempBlock(config.client_name, days)
                  onNotifySuccess('Статус OpenVPN обновлён')
                },
              ),
          },
          {
            label: '⛔ Блокировать до ручной разблокировки',
            hidden: !canManage || !isOpenVpn || isBlocked,
            onClick: () =>
              askConfirm(
                'Бессрочная блокировка OpenVPN',
                `Заблокировать клиента «${config.client_name}» до ручной разблокировки?`,
                async () => {
                  await openvpnPermanentBlock(config.client_name)
                  onNotifySuccess('Клиент заблокирован')
                },
              ),
          },
          {
            label: '🔓 Снять блокировку OpenVPN',
            hidden: !canManage || !isOpenVpn || !isBlocked,
            onClick: () =>
              runAction(async () => {
                await openvpnUnblock(config.client_name)
                onNotifySuccess('Блокировка снята')
              }),
          },
          {
            label: '⚡ Отключить сессию OpenVPN',
            hidden: !canManage || !isOpenVpn,
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
            label: '♻ Продлить сертификат',
            hidden: !isOwner || !isOpenVpn,
            onClick: handleRenewCert,
          },
          {
            label: '⛔ Временная блокировка WG/AWG',
            hidden: !canManage || isOpenVpn,
            onClick: () =>
              askNumber(
                'Временная блокировка WG/AWG',
                `Укажите срок блокировки для клиента «${config.client_name}»`,
                '7',
                async (days) => {
                  await wgTempBlock(config.client_name, days)
                  onNotifySuccess('Статус WG/AWG обновлён')
                },
              ),
          },
          {
            label: '⛔ Блокировать до ручной разблокировки',
            hidden: !canManage || isOpenVpn || isBlocked,
            onClick: () =>
              askConfirm(
                'Бессрочная блокировка WG/AWG',
                `Заблокировать клиента «${config.client_name}» до ручной разблокировки?`,
                async () => {
                  await wgPermanentBlock(config.client_name)
                  onNotifySuccess('Клиент заблокирован')
                },
              ),
          },
          {
            label: '🔓 Снять блокировку WG/AWG',
            hidden: !canManage || isOpenVpn || !['temp', 'permanent', 'expired'].includes(blockMode),
            onClick: handleWgUnblock,
          },
          {
            label: '♻ Продлить срок WG/AWG',
            hidden: !canManage || isOpenVpn,
            onClick: () =>
              askNumber(
                'Продлить срок WG/AWG',
                `Укажите срок продления для клиента «${config.client_name}»`,
                '30',
                async (days) => {
                  await wgSetExpiry(config.client_name, days, true)
                  onNotifySuccess('Срок WG/AWG обновлён')
                },
              ),
          },
          {
            label: '🗑 Удалить профиль',
            hidden: !canDelete,
            onClick: () =>
              askConfirm('Подтверждение удаления', `Удалить профиль «${config.client_name}»?`, async () => {
                await deleteConfig(config.id)
                onNotifySuccess(`Клиент «${config.client_name}» удалён`)
                onOpenChange(false)
              }),
          },
        ],
      },
      {
        title: 'Скачать',
        actions: [
          {
            label: '⬇️ Скачать VPN',
            hidden: !vpnFile,
            onClick: () => void onDownload(config, vpnFile!.path, vpnFile!.filename),
          },
          {
            label: '⬇️ Скачать AZ',
            hidden: !azFile,
            onClick: () => void onDownload(config, azFile!.path, azFile!.filename),
          },
        ],
      },
      {
        title: 'QR',
        actions: [
          {
            label: '📱 QR VPN',
            hidden: !vpnFile,
            onClick: () => void onQr(config, vpnFile!.path, vpnFile!.filename),
          },
          {
            label: '📱 QR AZ',
            hidden: !azFile,
            onClick: () => void onQr(config, azFile!.path, azFile!.filename),
          },
        ],
      },
      {
        title: 'Одноразовые ссылки',
        actions: [
          {
            label: '🔗 Ссылка VPN',
            hidden: !vpnFile,
            onClick: () => void handleOneTime(vpnFile!.path),
          },
          {
            label: '🔗 Ссылка AZ',
            hidden: !azFile,
            onClick: () => void handleOneTime(azFile!.path),
          },
        ],
      },
    ]

  const visibleGroups = actionGroups
    .map((g) => ({ ...g, actions: g.actions.filter((a) => !a.hidden) }))
    .filter((g) => g.actions.length > 0)

  const submitPrompt = async (e?: FormEvent, daysOverride?: number) => {
    e?.preventDefault()
    if (!pendingAction) return
    setPromptMode(null)
    await runAction(async () => {
      await pendingAction(daysOverride)
    })
    setPendingAction(null)
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{config.client_name}</DialogTitle>
            <DialogDescription>
              {protocolLabel(tab)}
              {config.description ? ` · ${config.description}` : ''}
            </DialogDescription>
          </DialogHeader>

          <section className="space-y-3">
            <h4 className="text-sm font-semibold">Действия</h4>
            {visibleGroups.length === 0 ? (
              <p className="text-sm text-muted-foreground">Для этого клиента нет доступных действий.</p>
            ) : (
              visibleGroups.map((group) => (
                <div key={group.title} className="rounded-lg border border-primary/25 bg-muted/20 p-3">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {group.title}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {group.actions.map((action) => (
                      <Button
                        key={action.label}
                        type="button"
                        variant="secondary"
                        size="sm"
                        disabled={busy}
                        onClick={action.onClick}
                        className="h-auto whitespace-normal py-1.5 text-left text-xs"
                      >
                        {action.label}
                      </Button>
                    ))}
                  </div>
                </div>
              ))
            )}
          </section>
        </DialogContent>
      </Dialog>

      <Dialog open={promptMode === 'number'} onOpenChange={(v) => !v && setPromptMode(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{promptTitle}</DialogTitle>
            <DialogDescription>{promptMessage}</DialogDescription>
          </DialogHeader>
          <form
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
              <Button type="button" variant="secondary" onClick={() => setPromptMode(null)}>
                Отмена
              </Button>
              <Button type="submit" disabled={busy}>
                Применить
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={promptMode === 'confirm'} onOpenChange={(v) => !v && setPromptMode(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{promptTitle}</DialogTitle>
            <DialogDescription>{promptMessage}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => setPromptMode(null)}>
              Отмена
            </Button>
            <Button type="button" variant="destructive" disabled={busy} onClick={() => void submitPrompt()}>
              Подтвердить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={promptMode === 'renew'} onOpenChange={(v) => !v && setPromptMode(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Продлить сертификат</DialogTitle>
            <DialogDescription>Укажите новый срок сертификата для клиента.</DialogDescription>
          </DialogHeader>
          <form
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
              <Button type="button" variant="secondary" onClick={() => setPromptMode(null)}>
                Отмена
              </Button>
              <Button type="submit" disabled={busy}>
                Сохранить
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={promptMode === 'expired-wg'} onOpenChange={(v) => !v && setPromptMode(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Срок действия истёк</DialogTitle>
            <DialogDescription>
              Клиент «{config.client_name}» отключён по истечении срока жизни. Для разблокировки необходимо продлить
              срок.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => setPromptMode(null)}>
              Закрыть
            </Button>
            <Button
              type="button"
              disabled={busy}
              onClick={() => {
                setPromptMode(null)
                askNumber(
                  'Продлить срок WG/AWG',
                  `Укажите срок продления для клиента «${config.client_name}»`,
                  '30',
                  async (days) => {
                    await wgSetExpiry(config.client_name, days, true)
                    onNotifySuccess('Срок WG/AWG обновлён')
                  },
                )
              }}
            >
              ♻ Продлить срок WG/AWG
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function protocolLabel(tab: ProtocolTab): string {
  if (tab === 'openvpn') return 'OpenVPN'
  if (tab === 'amneziawg') return 'AmneziaWG'
  return 'WireGuard'
}
