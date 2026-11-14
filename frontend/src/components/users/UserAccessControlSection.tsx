import { useEffect, useState } from 'react'
import {
  CalendarPlus,
  Copy,
  ExternalLink,
  KeyRound,
  Link2,
  Loader2,
  PauseCircle,
  PlayCircle,
  RefreshCw,
} from 'lucide-react'
import {
  ApiError,
  createUserPortalLink,
  getUserPortalLink,
  rotateUserPortalLink,
  updateUser,
} from '@/api/client'
import { isoToDateInput } from '@/lib/accessUntil'
import { portalActionConfirm } from '@/lib/portalConfirm'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import { extendUserAccess, resumeUser, suspendUser } from '@/api/users'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import UnlockCodeCreateDialog from '@/components/dashboard/UnlockCodeCreateDialog'
import UserSection from './UserSection'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { formatDate, formatDateTime, parseTimestamp } from '@/lib/datetime'
import type { UserProvisioningCard, UserProvisionSummary } from '@/types'
import SuspendUserDialog, { type SuspendUserPayload } from './SuspendUserDialog'

interface UserAccessControlSectionProps {
  card: UserProvisioningCard
  onRefresh: () => void
}


/** Продление доступа и приостановка (модуль «Пользователи (абоненты)»). */
function AccessLifecycleCard({
  user,
  busy,
  onExtend,
  onSetAccessUntil,
  onSuspend,
  onResume,
  onError,
}: {
  user: UserProvisionSummary
  busy: boolean
  onExtend: (days: number) => void
  onSetAccessUntil: (value: string | null) => void
  onSuspend: (data: SuspendUserPayload) => void
  onResume: (notifyTelegram: boolean) => void
  onError: (message: string) => void
}) {
  const [suspendOpen, setSuspendOpen] = useState(false)
  // Возобновление по умолчанию пишет абоненту в Telegram.
  const [resumeNotify, setResumeNotify] = useState(true)
  const [customDays, setCustomDays] = useState('')
  // Дата окончания (включительно) — из API приходит ISO, input[type=date] ждёт YYYY-MM-DD.
  const [customDate, setCustomDate] = useState(isoToDateInput(user.access_until))
  // Продление кнопками меняет срок — подтягиваем новую дату в календарь.
  useEffect(() => {
    setCustomDate(isoToDateInput(user.access_until))
  }, [user.access_until])

  const suspended = Boolean(user.suspended_at)
  // Администраторов приостановить нельзя (API отклоняет) — прячем действие.
  const canSuspend = user.role !== 'admin'
  const accessUntilMs = parseTimestamp(user.access_until)?.getTime()
  const accessExpired = accessUntilMs != null && accessUntilMs < Date.now()

  const handleCustomExtend = () => {
    const days = Number.parseInt(customDays, 10)
    if (!Number.isFinite(days) || days < 1 || days > 3650) {
      onError('Укажите число дней от 1 до 3650')
      return
    }
    onExtend(days)
  }

  return (
    <>
      <UserSection
        icon={CalendarPlus}
        title="Срок доступа"
        description={
          user.access_until
            ? `Сейчас доступ до ${formatDate(user.access_until)}. Продление сбрасывает счётчик трафика.`
            : 'Бессрочный доступ. Продление сбрасывает счётчик трафика.'
        }
        actions={
          suspended ? (
            <Badge variant="destructive" className="text-[10px]">
              Приостановлен
            </Badge>
          ) : accessExpired ? (
            <Badge variant="destructive" className="text-[10px]">
              Истёк
            </Badge>
          ) : (
            <Badge variant="success" className="text-[10px]">
              Активен
            </Badge>
          )
        }
      >
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onExtend(30)}
              disabled={busy}
            >
              +30 дней
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onExtend(60)}
              disabled={busy}
            >
              +60 дней
            </Button>
            <div className="flex items-center gap-1.5">
              <Input
                value={customDays}
                onChange={(e) => setCustomDays(e.target.value)}
                placeholder="дней"
                inputMode="numeric"
                aria-label="Свой срок продления в днях"
                className="h-9 w-20"
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={handleCustomExtend}
                disabled={busy || customDays.trim() === ''}
              >
                Продлить
              </Button>
            </div>
          </div>

          <div className="space-y-1.5 rounded-lg border bg-muted/20 px-3 py-2.5">
            <p className="text-xs font-medium text-muted-foreground">Дата окончания доступа</p>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                type="date"
                value={customDate}
                onChange={(e) => setCustomDate(e.target.value)}
                aria-label="Дата окончания доступа"
                className="h-9 w-44"
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => onSetAccessUntil(customDate)}
                disabled={busy || customDate === ''}
              >
                Установить дату
              </Button>
              {user.access_until && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => onSetAccessUntil(null)}
                  disabled={busy}
                >
                  Бессрочно
                </Button>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Доступ действует до конца выбранного дня. Продление по дням считается от текущего
              срока.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/20 px-3 py-2.5">
            {suspended ? (
              <>
                <Button type="button" size="sm" onClick={() => onResume(resumeNotify)} disabled={busy}>
                  <PlayCircle size={15} />
                  Возобновить
                </Button>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Checkbox
                    checked={resumeNotify}
                    onCheckedChange={(value) => setResumeNotify(value === true)}
                    aria-label="Уведомить в Telegram о возобновлении"
                  />
                  Уведомить в Telegram
                </label>
              </>
            ) : canSuspend ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setSuspendOpen(true)}
                disabled={busy}
              >
                <PauseCircle size={15} />
                Приостановить
              </Button>
            ) : null}
          </div>
          {suspended && user.suspend_reason && (
            <p className="text-xs text-muted-foreground">
              Причина: {user.suspend_reason}
              {user.suspend_reason_visible ? '' : ' (скрыта от пользователя)'}
            </p>
          )}
        </div>
      </UserSection>

      <SuspendUserDialog
        open={suspendOpen}
        onOpenChange={setSuspendOpen}
        username={user.username}
        busy={busy}
        onConfirm={onSuspend}
      />
    </>
  )
}

/** Постоянная ссылка клиентского портала: все профили абонента в одном месте. */
function ClientPortalCard({
  user,
  onError,
}: {
  user: UserProvisionSummary
  onError: (message: string) => void
}) {
  const { success } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const [url, setUrl] = useState<string | null>(null)
  const [expiresAt, setExpiresAt] = useState<string | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)

  const applyLink = async (
    key: string,
    action: () => Promise<{ url: string; expires_at?: string | null }>,
    message: string,
  ) => {
    setBusyKey(key)
    try {
      const link = await action()
      setUrl(link.url)
      setExpiresAt(link.expires_at ?? null)
      await navigator.clipboard.writeText(link.url)
      success(message)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Ошибка ссылки портала')
    } finally {
      setBusyKey(null)
    }
  }

  const copyLink = (create: boolean) =>
    applyLink(
      create ? 'create' : 'copy',
      () => (create ? createUserPortalLink(user.id) : getUserPortalLink(user.id)),
      create ? 'Ссылка портала создана и скопирована' : 'Ссылка портала скопирована',
    )

  const rotateLink = () =>
    applyLink(
      'rotate',
      () => rotateUserPortalLink(user.id),
      'Ссылка портала перевыпущена и скопирована',
    )

  return (
    <>
      <UserSection
        icon={Link2}
        title="Клиентский портал"
        description="Постоянная ссылка со всеми профилями абонента: открывается на устройстве без входа в панель, оттуда можно скачать нужный файл."
      >
        <div className="space-y-3">
          {url ? (
            <div className="space-y-1">
              <p className="break-all rounded-lg border bg-muted/20 px-3 py-2 font-mono text-xs">
                {url}
              </p>
              <p className="text-xs text-muted-foreground">
                {expiresAt
                  ? `Ссылка действует до ${formatDateTime(expiresAt)}`
                  : 'Срок действия ссылки не ограничен'}
              </p>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              Ссылка создаётся один раз и не меняется — отправьте её абоненту в Telegram или
              скопируйте.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => void copyLink(url == null)}
              disabled={busyKey !== null}
            >
              {busyKey === 'create' || busyKey === 'copy' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Copy size={14} />
              )}
              {url ? 'Скопировать' : 'Получить ссылку'}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!url}
              onClick={() => {
                if (url) window.open(url, '_blank', 'noopener,noreferrer')
              }}
            >
              <ExternalLink size={14} />
              Открыть
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={url == null || busyKey !== null}
              onClick={() =>
                confirm({
                  ...portalActionConfirm('rotate', user.username, 'пользователю'),
                  destructive: true,
                  onConfirm: rotateLink,
                })
              }
            >
              {busyKey === 'rotate' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              Перевыпустить
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Отозвать ссылку или выпустить новую для всех абонентов можно в разделе «Подписка».
          </p>
        </div>
      </UserSection>
      <ConfirmDialogHost dialogProps={dialogProps} />
    </>
  )
}

export default function UserAccessControlSection({
  card,
  onRefresh,
}: UserAccessControlSectionProps) {
  const { user } = card
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  // Приостановка/продление — только при включённом модуле «Пользователи (абоненты)».
  const provisioningOn = isEnabled('user_provisioning')
  // Ссылка портала — только при включённом «Клиентском портале».
  const clientPortalEnabled = isEnabled('client_portal')
  // Ключ продления — при включённых unlock-кодах и хотя бы одном VPN-протоколе.
  const unlockEnabled = isEnabled('unlock_codes')
  const unlockProtocols = (
    [
      { id: 'openvpn', keys: ['openvpn'] },
      { id: 'wireguard', keys: ['wireguard', 'amneziawg'] },
      { id: 'amneziawg2', keys: ['awg2'] },
    ] as const
  )
    .filter((p) => p.keys.some((k) => isEnabled(k)))
    .map((p) => p.id)

  const [busy, setBusy] = useState(false)
  const [unlockOpen, setUnlockOpen] = useState(false)

  const run = async (action: () => Promise<void>, message: string) => {
    setBusy(true)
    try {
      await action()
      success(message)
      onRefresh()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка выполнения операции')
    } finally {
      setBusy(false)
    }
  }

  const handleExtend = (days: number) => {
    void run(async () => {
      await extendUserAccess(user.id, days)
    }, `Доступ продлён на ${days} дн.`)
  }

  const handleSetAccessUntil = (value: string | null) => {
    void run(
      async () => {
        await updateUser(user.id, { access_until: value })
      },
      value
        ? `Доступ установлен до ${formatDate(`${value}T23:59:59`)}`
        : 'Срок доступа снят — доступ бессрочный',
    )
  }

  const handleSuspend = (data: {
    reason: string | null
    show_reason: boolean
    notify_telegram: boolean
  }) => {
    void run(async () => {
      await suspendUser(user.id, data)
    }, 'Доступ приостановлен')
  }

  const handleResume = (notifyTelegram: boolean) => {
    void run(async () => {
      await resumeUser(user.id, { notify_telegram: notifyTelegram })
    }, 'Доступ возобновлён')
  }

  return (
    <>
      <div className="space-y-4">
        {provisioningOn && (
          <AccessLifecycleCard
            user={user}
            busy={busy}
            onExtend={handleExtend}
            onSetAccessUntil={handleSetAccessUntil}
            onSuspend={handleSuspend}
            onResume={handleResume}
            onError={notifyError}
          />
        )}
        {unlockEnabled && unlockProtocols.length > 0 ? (
          <UserSection
            icon={KeyRound}
            title="Ключ продления"
            description="Создать unlock-ключ для абонента и отправить в Telegram, если он привязан."
          >
            <Button
              type="button"
              onClick={() => setUnlockOpen(true)}
              className="w-full sm:w-auto"
            >
              <KeyRound size={15} /> Создать ключ
            </Button>
          </UserSection>
        ) : null}
        {clientPortalEnabled && <ClientPortalCard user={user} onError={notifyError} />}
      </div>

      {unlockEnabled && unlockProtocols.length > 0 ? (
        <UnlockCodeCreateDialog
          open={unlockOpen}
          onOpenChange={setUnlockOpen}
          availableProtocols={unlockProtocols}
          initialProtocols={unlockProtocols}
          boundUser={{ id: user.id, username: user.username }}
          telegramBound={Boolean(user.telegram_id)}
          targetUserId={user.id}
          onCreated={() => onRefresh()}
        />
      ) : null}
    </>
  )
}
