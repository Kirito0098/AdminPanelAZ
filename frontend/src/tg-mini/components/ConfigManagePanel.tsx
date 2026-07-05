import { useEffect, useState } from 'react'
import {
  Ban,
  ChevronDown,
  Loader2,
  ShieldOff,
  Trash2,
  UserRound,
} from 'lucide-react'
import { ApiError } from '@/api/client'
import ConfigOwnerSelect from '@/components/dashboard/ConfigOwnerSelect'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { formatBlockStatus } from '@/lib/configCardUtils'
import { cn } from '@/lib/utils'
import {
  deleteTgPanelConfig,
  getTgClientPolicy,
  getTgPanelConfig,
  getTgPanelUsers,
  tgOpenvpnPermanentBlock,
  tgOpenvpnTempBlock,
  tgOpenvpnUnblock,
  tgWgPermanentBlock,
  tgWgTempBlock,
  tgWgUnblock,
  updateTgPanelConfig,
} from '@/tg-mini/api'
import type { ClientAccessPolicy, TgMiniConfig, User, VpnType } from '@/types'
import type { ReactNode } from 'react'

interface ConfigManagePanelProps {
  config: TgMiniConfig
  isAdmin: boolean
  onDeleted: () => void
  onUpdated: () => void
}

type BusyAction = 'save' | 'renew' | 'owner' | 'temp-block' | 'perm-block' | 'unblock' | 'delete' | null

function policyForConfig(policy: ClientAccessPolicy | null) {
  const blockMode = (policy?.block_mode || 'none').toLowerCase()
  const isBlocked =
    Boolean(policy?.is_blocked) ||
    blockMode === 'temp' ||
    blockMode === 'permanent' ||
    blockMode === 'expired' ||
    blockMode === 'traffic_limit'
  return {
    isBlocked,
    blockMode,
    status: formatBlockStatus(policy ?? undefined),
  }
}

async function blockClient(vpnType: VpnType, clientName: string, days: number) {
  if (vpnType === 'openvpn') await tgOpenvpnTempBlock(clientName, days)
  else await tgWgTempBlock(clientName, days)
}

async function permanentBlockClient(vpnType: VpnType, clientName: string) {
  if (vpnType === 'openvpn') await tgOpenvpnPermanentBlock(clientName)
  else await tgWgPermanentBlock(clientName)
}

async function unblockClient(vpnType: VpnType, clientName: string) {
  if (vpnType === 'openvpn') await tgOpenvpnUnblock(clientName)
  else await tgWgUnblock(clientName)
}

function ManageSection({
  title,
  summary,
  defaultOpen = true,
  tone,
  children,
}: {
  title: string
  summary?: string
  defaultOpen?: boolean
  tone?: 'danger'
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <section className={cn('tg-mini-manage-section', tone === 'danger' && 'is-danger')}>
      <button
        type="button"
        className="tg-mini-manage-section-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="min-w-0 text-left">
          <span className="tg-mini-manage-section-title">{title}</span>
          {!open && summary ? (
            <span className="tg-mini-manage-section-summary">{summary}</span>
          ) : null}
        </span>
        <ChevronDown size={18} className={cn('tg-mini-manage-chevron', open && 'is-open')} aria-hidden />
      </button>
      {open && <div className="tg-mini-manage-section-body">{children}</div>}
    </section>
  )
}

export default function ConfigManagePanel({ config, isAdmin, onDeleted, onUpdated }: ConfigManagePanelProps) {
  const [loading, setLoading] = useState(true)
  const [description, setDescription] = useState('')
  const [certDays, setCertDays] = useState('3650')
  const [ownerId, setOwnerId] = useState<number | null>(null)
  const [ownerUsername, setOwnerUsername] = useState<string | undefined>()
  const [users, setUsers] = useState<User[]>([])
  const [policy, setPolicy] = useState<ClientAccessPolicy | null>(null)
  const [blockDays, setBlockDays] = useState('7')
  const [confirmPermBlock, setConfirmPermBlock] = useState(false)
  const [busy, setBusy] = useState<BusyAction>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [feedback, setFeedback] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  const vpnType = config.vpn_type as VpnType
  const { isBlocked, status: blockStatus } = policyForConfig(policy)

  const reloadPolicy = async () => {
    if (!isAdmin) return
    try {
      setPolicy(await getTgClientPolicy(config.client_name, vpnType))
    } catch {
      setPolicy(null)
    }
  }

  useEffect(() => {
    setLoading(true)
    setConfirmDelete(false)
    setConfirmPermBlock(false)
    setFeedback(null)
    void Promise.all([
      getTgPanelConfig(config.id),
      isAdmin ? getTgClientPolicy(config.client_name, vpnType) : Promise.resolve(null),
      isAdmin ? getTgPanelUsers() : Promise.resolve([] as User[]),
    ])
      .then(([details, policyData, panelUsers]) => {
        setDescription(details.description ?? '')
        setCertDays(String(details.cert_expire_days ?? 3650))
        setOwnerId(details.owner_id)
        setOwnerUsername(details.owner_username)
        setPolicy(policyData)
        setUsers(panelUsers)
      })
      .catch((err) => {
        setFeedback({
          tone: 'error',
          text: err instanceof ApiError ? err.message : 'Не удалось загрузить данные',
        })
      })
      .finally(() => setLoading(false))
  }, [config.id, config.client_name, isAdmin, vpnType])

  const handleSaveDescription = async () => {
    setBusy('save')
    setFeedback(null)
    try {
      await updateTgPanelConfig(config.id, { description: description.trim() || '' })
      setFeedback({ tone: 'success', text: 'Описание сохранено' })
      onUpdated()
    } catch (err) {
      setFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Ошибка сохранения' })
    } finally {
      setBusy(null)
    }
  }

  const handleSaveOwner = async () => {
    if (!ownerId) {
      setFeedback({ tone: 'error', text: 'Выберите владельца' })
      return
    }
    setBusy('owner')
    setFeedback(null)
    try {
      await updateTgPanelConfig(config.id, { owner_id: ownerId })
      setFeedback({ tone: 'success', text: 'Владелец изменён' })
      onUpdated()
    } catch (err) {
      setFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Ошибка смены владельца' })
    } finally {
      setBusy(null)
    }
  }

  const handleRenewCert = async () => {
    const days = Number(certDays)
    if (!Number.isFinite(days) || days < 1 || days > 3650) {
      setFeedback({ tone: 'error', text: 'Срок сертификата: от 1 до 3650 дней' })
      return
    }
    setBusy('renew')
    setFeedback(null)
    try {
      await updateTgPanelConfig(config.id, { cert_expire_days: days })
      setFeedback({ tone: 'success', text: 'Сертификат обновлён' })
      onUpdated()
    } catch (err) {
      setFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Ошибка обновления сертификата' })
    } finally {
      setBusy(null)
    }
  }

  const handleTempBlock = async () => {
    const days = Number(blockDays)
    if (!Number.isFinite(days) || days < 1 || days > 3650) {
      setFeedback({ tone: 'error', text: 'Срок блокировки: от 1 до 3650 дней' })
      return
    }
    setBusy('temp-block')
    setFeedback(null)
    try {
      await blockClient(vpnType, config.client_name, days)
      setFeedback({ tone: 'success', text: `Клиент заблокирован на ${days} дн.` })
      await reloadPolicy()
      onUpdated()
    } catch (err) {
      setFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Ошибка блокировки' })
    } finally {
      setBusy(null)
    }
  }

  const handlePermanentBlock = async () => {
    if (!confirmPermBlock) {
      setConfirmPermBlock(true)
      return
    }
    setBusy('perm-block')
    setFeedback(null)
    try {
      await permanentBlockClient(vpnType, config.client_name)
      setFeedback({ tone: 'success', text: 'Клиент заблокирован до ручной разблокировки' })
      setConfirmPermBlock(false)
      await reloadPolicy()
      onUpdated()
    } catch (err) {
      setFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Ошибка блокировки' })
      setConfirmPermBlock(false)
    } finally {
      setBusy(null)
    }
  }

  const handleUnblock = async () => {
    setBusy('unblock')
    setFeedback(null)
    try {
      await unblockClient(vpnType, config.client_name)
      setFeedback({ tone: 'success', text: 'Клиент разблокирован' })
      await reloadPolicy()
      onUpdated()
    } catch (err) {
      setFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Ошибка разблокировки' })
    } finally {
      setBusy(null)
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setBusy('delete')
    setFeedback(null)
    try {
      await deleteTgPanelConfig(config.id)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      onDeleted()
    } catch (err) {
      setFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Ошибка удаления' })
      setConfirmDelete(false)
    } finally {
      setBusy(null)
    }
  }

  if (loading) {
    return (
      <div className="tg-mini-center py-12">
        <Loader2 size={24} className="animate-spin text-muted-foreground" aria-hidden />
        <p className="text-sm text-muted-foreground">Загрузка настроек…</p>
      </div>
    )
  }

  return (
    <div className="tg-mini-manage-stack">
      <ManageSection
        title="Основное"
        summary={description.trim() || 'Без описания'}
        defaultOpen
      >
        <div className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="tg-mini-manage-description">Описание</Label>
            <Input
              id="tg-mini-manage-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Заметка для себя или команды"
              disabled={busy != null}
            />
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="w-full"
            disabled={busy != null}
            onClick={() => void handleSaveDescription()}
          >
            {busy === 'save' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : 'Сохранить'}
          </Button>
        </div>
      </ManageSection>

      {isAdmin && (
        <ManageSection title="Владелец" summary={ownerUsername ? `@${ownerUsername}` : undefined} defaultOpen={false}>
          <div className="space-y-3">
            <ConfigOwnerSelect
              id="tg-mini-manage-owner"
              users={users}
              value={ownerId}
              onChange={setOwnerId}
              disabled={busy != null}
              currentOwner={ownerId && ownerUsername ? { id: ownerId, username: ownerUsername } : undefined}
            />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="w-full gap-2"
              disabled={busy != null}
              onClick={() => void handleSaveOwner()}
            >
              {busy === 'owner' ? (
                <Loader2 size={16} className="animate-spin" aria-hidden />
              ) : (
                <UserRound size={16} aria-hidden />
              )}
              Применить
            </Button>
          </div>
        </ManageSection>
      )}

      {config.vpn_type === 'openvpn' && (
        <ManageSection title="Сертификат" summary={`${certDays} дн.`} defaultOpen={false}>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="tg-mini-renew-cert">Новый срок (дней)</Label>
              <Input
                id="tg-mini-renew-cert"
                type="number"
                min={1}
                max={3650}
                value={certDays}
                onChange={(e) => setCertDays(e.target.value)}
                disabled={busy != null}
              />
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="w-full"
              disabled={busy != null}
              onClick={() => void handleRenewCert()}
            >
              {busy === 'renew' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : 'Обновить сертификат'}
            </Button>
          </div>
        </ManageSection>
      )}

      {isAdmin && (
        <ManageSection
          title="Доступ"
          summary={blockStatus.value}
          defaultOpen={isBlocked}
          tone={isBlocked ? 'danger' : undefined}
        >
          <div className="space-y-3">
            <p
              className={cn(
                'text-sm',
                blockStatus.tone === 'danger' ? 'text-destructive' : 'text-muted-foreground',
              )}
            >
              Сейчас: {blockStatus.value}
            </p>
            {!isBlocked ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="tg-mini-block-days">Временная блокировка (дней)</Label>
                  <Input
                    id="tg-mini-block-days"
                    type="number"
                    min={1}
                    max={3650}
                    value={blockDays}
                    onChange={(e) => setBlockDays(e.target.value)}
                    disabled={busy != null}
                  />
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="w-full gap-2"
                  disabled={busy != null}
                  onClick={() => void handleTempBlock()}
                >
                  {busy === 'temp-block' ? (
                    <Loader2 size={16} className="animate-spin" aria-hidden />
                  ) : (
                    <Ban size={16} aria-hidden />
                  )}
                  Заблокировать
                </Button>
                <Button
                  type="button"
                  variant={confirmPermBlock ? 'destructive' : 'outline'}
                  size="sm"
                  className="w-full gap-2"
                  disabled={busy != null}
                  onClick={() => void handlePermanentBlock()}
                >
                  {busy === 'perm-block' ? (
                    <Loader2 size={16} className="animate-spin" aria-hidden />
                  ) : (
                    <Ban size={16} aria-hidden />
                  )}
                  {confirmPermBlock ? 'Подтвердить постоянную' : 'Постоянная блокировка'}
                </Button>
                {confirmPermBlock && (
                  <Button type="button" variant="ghost" size="sm" className="w-full" onClick={() => setConfirmPermBlock(false)}>
                    Отмена
                  </Button>
                )}
              </>
            ) : (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="w-full gap-2"
                disabled={busy != null}
                onClick={() => void handleUnblock()}
              >
                {busy === 'unblock' ? (
                  <Loader2 size={16} className="animate-spin" aria-hidden />
                ) : (
                  <ShieldOff size={16} aria-hidden />
                )}
                Разблокировать
              </Button>
            )}
          </div>
        </ManageSection>
      )}

      <ManageSection title="Удаление" summary="Безвозвратно" defaultOpen={false} tone="danger">
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Конфиг и файлы профиля будут удалены с активного узла
          </p>
          <Button
            type="button"
            variant={confirmDelete ? 'destructive' : 'outline'}
            size="sm"
            className="w-full gap-2"
            disabled={busy != null}
            onClick={() => void handleDelete()}
          >
            {busy === 'delete' ? (
              <Loader2 size={16} className="animate-spin" aria-hidden />
            ) : (
              <Trash2 size={16} aria-hidden />
            )}
            {confirmDelete ? 'Подтвердить удаление' : 'Удалить конфиг'}
          </Button>
          {confirmDelete && (
            <Button type="button" variant="ghost" size="sm" className="w-full" onClick={() => setConfirmDelete(false)}>
              Отмена
            </Button>
          )}
        </div>
      </ManageSection>

      {feedback && (
        <p
          className={
            feedback.tone === 'error'
              ? 'text-destructive px-1 text-sm'
              : 'px-1 text-sm text-emerald-600 dark:text-emerald-400'
          }
        >
          {feedback.text}
        </p>
      )}
    </div>
  )
}
