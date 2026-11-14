import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Globe, KeyRound, Loader2, Settings2, Ticket, Trash2, Users } from 'lucide-react'
import {
  ApiError,
  getPortalPublishStatus,
  getSecuritySettings,
  updateSecuritySettings,
} from '@/api/client'
import UnlockCodeCreateDialog from '@/components/dashboard/UnlockCodeCreateDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import { DOCS } from '@/lib/docsUrls'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { formatDateTime } from '@/lib/datetime'
import {
  isUnlockCodeExhausted,
  unlockCodeRedeemedCount,
  unlockCodeStatusLabel,
} from '@/lib/unlockCodeStatus'
import { unlockCodeRevokeConfirm } from '@/lib/unlockCodeConfirm'
import { cn } from '@/lib/utils'
import { protocolLabel } from '@/lib/vpnTypes'
import type { PortalPublishStatus, UnlockCodeRecord } from '@/types'
import { getUnlockCodes, revokeUnlockCode, type UnlockCodeProtocol } from '@/api/unlockCodes'

type SubscriptionPageProps = {
  /** Внутри вкладки «Портал и коды»: без своего заголовка и внешних отступов страницы. */
  embedded?: boolean
}

export default function SubscriptionPage({ embedded = false }: SubscriptionPageProps) {
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const { isEnabled } = useFeatureModules()
  const clientPortalEnabled = isEnabled('client_portal')
  const unlockCodesEnabled = isEnabled('unlock_codes')
  const openvpnEnabled = isEnabled('openvpn')
  const wireguardEnabled = isEnabled('wireguard') || isEnabled('amneziawg')
  const awg2Enabled = isEnabled('awg2')

  const [portalStatus, setPortalStatus] = useState<PortalPublishStatus | null>(null)
  const [loading, setLoading] = useState(clientPortalEnabled)
  const [unlockCodes, setUnlockCodes] = useState<UnlockCodeRecord[]>([])
  const [unlockCodesLoading, setUnlockCodesLoading] = useState(false)
  const [unlockCodesBusyId, setUnlockCodesBusyId] = useState<number | null>(null)
  const [unlockCreateOpen, setUnlockCreateOpen] = useState(false)
  const [linkTtlDays, setLinkTtlDays] = useState(30)
  const [linkTtlSaving, setLinkTtlSaving] = useState(false)

  useEffect(() => {
    if (!clientPortalEnabled) {
      setPortalStatus(null)
      setLoading(false)
      return
    }
    setLoading(true)
    void getPortalPublishStatus()
      .then(setPortalStatus)
      .catch((err) => {
        setPortalStatus(null)
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
      })
      .finally(() => setLoading(false))
  }, [clientPortalEnabled, notifyError])

  useEffect(() => {
    if (!clientPortalEnabled) return
    void getSecuritySettings()
      .then((settings) => setLinkTtlDays(settings.portal_link_ttl_days))
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки настроек портала'))
  }, [clientPortalEnabled, notifyError])

  useEffect(() => {
    if (!unlockCodesEnabled) {
      setUnlockCodes([])
      setUnlockCodesLoading(false)
      return
    }
    setUnlockCodesLoading(true)
    void getUnlockCodes()
      .then(setUnlockCodes)
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки unlock-ключей'))
      .finally(() => setUnlockCodesLoading(false))
  }, [notifyError, unlockCodesEnabled])

  const availableUnlockProtocols: UnlockCodeProtocol[] = []
  if (openvpnEnabled) availableUnlockProtocols.push('openvpn')
  if (wireguardEnabled) availableUnlockProtocols.push('wireguard')
  if (awg2Enabled) availableUnlockProtocols.push('amneziawg2')

  const refreshUnlockCodes = async () => {
    if (!unlockCodesEnabled) return
    setUnlockCodesLoading(true)
    try {
      setUnlockCodes(await getUnlockCodes())
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки unlock-ключей')
    } finally {
      setUnlockCodesLoading(false)
    }
  }

  const handleRevokeUnlockCode = async (code: UnlockCodeRecord) => {
    setUnlockCodesBusyId(code.id)
    try {
      await revokeUnlockCode(code.id)
      success('Ключ отозван')
      await refreshUnlockCodes()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось отозвать ключ')
    } finally {
      setUnlockCodesBusyId(null)
    }
  }

  const confirmRevokeUnlockCode = (code: UnlockCodeRecord) => {
    confirm({
      ...unlockCodeRevokeConfirm(code.code),
      destructive: true,
      onConfirm: () => handleRevokeUnlockCode(code),
    })
  }

  const saveLinkTtl = async () => {
    setLinkTtlSaving(true)
    try {
      const updated = await updateSecuritySettings({ portal_link_ttl_days: linkTtlDays })
      setLinkTtlDays(updated.portal_link_ttl_days)
      success('Срок жизни ссылки портала сохранён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить срок жизни ссылки')
    } finally {
      setLinkTtlSaving(false)
    }
  }

  const portalModeBlocked = portalStatus?.portal_mode_supported === false
  const portalAccessUrl = portalStatus?.portal_access_url ?? ''
  if (loading && clientPortalEnabled) {
    return <Spinner label="Загрузка…" className={embedded ? 'py-8' : 'py-12'} />
  }

  return (
    <div className={embedded ? 'space-y-4' : 'space-y-6'}>
      {!embedded && (
        <PageSectionHeader
          icon={Ticket}
          title="Подписка"
          description="Клиентский портал и unlock-ключи продления доступа"
          docsHref={DOCS.subscription}
        />
      )}

      {clientPortalEnabled && (
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
            <div className="min-w-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <Globe size={18} />
                Клиентский портал
              </CardTitle>
              <CardDescription className="mt-1.5">
                Домен и публикация портала настраиваются в «Настройки → Адрес сайта и HTTPS».
              </CardDescription>
            </div>
            {portalStatus ? (
              <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
                <Badge variant={portalStatus.portal_ready ? 'success' : 'warning'}>
                  {portalStatus.portal_ready ? 'Готов' : 'Нужна настройка'}
                </Badge>
                {portalStatus.active_publish_mode ? (
                  <Badge variant="outline">{portalStatus.active_publish_mode}</Badge>
                ) : null}
              </div>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-4">
            {portalModeBlocked ? (
              <SettingsAlert variant="warning" title="Портал недоступен в текущем режиме">
                <p>
                  {portalStatus?.portal_mode_block_reason ||
                    'Клиентский портал доступен только при публикации через Nginx.'}
                </p>
                <p className="mt-1.5">
                  <Link
                    to="/settings/vpn_network"
                    className="font-medium text-primary underline-offset-4 hover:underline"
                  >
                    Открыть «Адрес сайта и HTTPS»
                  </Link>{' '}
                  и выберите стек «Через Nginx».
                </p>
              </SettingsAlert>
            ) : null}

            {portalStatus ? (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border bg-muted/20 px-3 py-2.5">
                    <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      Домен
                    </p>
                    <p className="mt-1 break-all font-mono text-sm">
                      {portalStatus.portal_domain || 'не задан'}
                    </p>
                  </div>
                  <div className="rounded-xl border bg-muted/20 px-3 py-2.5">
                    <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      Корень портала
                    </p>
                    <p className="mt-1 break-all font-mono text-sm">
                      {portalAccessUrl || 'не настроен'}
                    </p>
                  </div>
                </div>

                <div className="flex flex-col gap-3 rounded-xl border bg-muted/20 p-3 sm:flex-row sm:items-end sm:justify-between">
                  <div className="max-w-xs space-y-1.5">
                    <Label htmlFor="portal-link-ttl" className="text-xs">
                      Срок жизни ссылки портала, дней (0 — бессрочно)
                    </Label>
                    <Input
                      id="portal-link-ttl"
                      type="number"
                      min={0}
                      max={3650}
                      value={linkTtlDays}
                      onChange={(e) => setLinkTtlDays(Number(e.target.value))}
                    />
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void saveLinkTtl()}
                    disabled={linkTtlSaving}
                  >
                    {linkTtlSaving ? 'Сохранение…' : 'Сохранить'}
                  </Button>
                </div>

                {portalStatus.warnings.length > 0 ? (
                  <div className="space-y-1">
                    {portalStatus.warnings.map((w) => (
                      <p key={w} className="text-xs text-amber-700 dark:text-amber-400">
                        {w}
                      </p>
                    ))}
                  </div>
                ) : null}

                <div className="flex flex-wrap gap-2">
                  <Button asChild variant="outline" size="sm" className="gap-1.5">
                    <Link to="/settings/vpn_network">
                      <Settings2 size={14} />
                      Настроить домен
                    </Link>
                  </Button>
                  <Button asChild variant="outline" size="sm" className="gap-1.5">
                    <Link to="/users">
                      <Users size={14} />
                      Ссылки пользователей
                    </Link>
                  </Button>
                </div>

                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">
                    Персональные ссылки открывают портал — они в карточке абонента.
                  </p>
                  {portalStatus.dns_hint ? (
                    <p className="text-xs text-muted-foreground">{portalStatus.dns_hint}</p>
                  ) : null}
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>
      )}

      {unlockCodesEnabled && availableUnlockProtocols.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <KeyRound size={18} />
                Unlock-ключи
              </CardTitle>
              <CardDescription className="mt-1.5">
                Создание и отзыв ключей продления для клиентов. Код общий; повторная активация
                блокируется по паре имя клиента + узел.
              </CardDescription>
            </div>
            {unlockCodes.length > 0 && (
              <Badge variant="secondary" className="shrink-0">
                {unlockCodes.length}
              </Badge>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                className="gap-1.5"
                onClick={() => setUnlockCreateOpen(true)}
              >
                <KeyRound size={16} />
                Создать ключ
              </Button>
            </div>

            {unlockCodesLoading ? (
              <div className="flex items-center justify-center rounded-xl border border-dashed bg-muted/10 px-4 py-8 text-sm text-muted-foreground">
                <Loader2 size={16} className="mr-2 animate-spin" />
                Загрузка ключей...
              </div>
            ) : unlockCodes.length === 0 ? (
              <div className="rounded-xl border border-dashed bg-muted/10 px-4 py-8 text-center text-sm text-muted-foreground">
                Пока нет unlock-ключей. Создайте первый ключ продления.
              </div>
            ) : (
              <div className="space-y-2">
                {unlockCodes.map((code) => {
                  const isRevoked = Boolean(code.revoked_at)
                  const redeemed = unlockCodeRedeemedCount(code)
                  const exhausted = isUnlockCodeExhausted(code)
                  const statusLabel = unlockCodeStatusLabel(code)
                  const protocolList = code.protocols.map(protocolLabel).join(', ')
                  const redemptions = code.redemptions ?? []
                  return (
                    <div
                      key={code.id}
                      className={cn(
                        'flex flex-col gap-3 rounded-xl border bg-card/60 p-3 sm:flex-row sm:items-start sm:justify-between',
                        exhausted && !isRevoked && 'border-amber-500/30 bg-amber-500/5',
                        isRevoked && 'opacity-70',
                      )}
                    >
                      <div className="min-w-0 space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="break-all font-mono text-sm font-semibold">{code.code}</p>
                          <Badge variant={code.mode === 'multi' ? 'default' : 'secondary'}>
                            {code.mode === 'multi' ? 'multi' : 'single'}
                          </Badge>
                          {statusLabel === 'Отозван' && <Badge variant="destructive">Отозван</Badge>}
                          {statusLabel === 'Активирован' && <Badge variant="success">Активирован</Badge>}
                          {statusLabel === 'Исчерпан' && <Badge variant="warning">Исчерпан</Badge>}
                          {statusLabel === 'Частично' && <Badge variant="outline">Частично</Badge>}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {code.grant_days} дн. · активаций {redeemed} / {code.max_redemptions}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {code.target_user_id
                            ? 'Ключ для абонента'
                            : (code.allowed_client_names?.length ?? 0) > 0
                              ? 'Профиль'
                              : `Протоколы: ${protocolList || '—'}`}{' '}
                          · создан {formatDateTime(code.created_at)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Истекает: {formatDateTime(code.code_expires_at)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {code.target_user_id
                            ? `Абонент: ${code.target_user_name ?? code.target_user_id}`
                            : `Клиенты: ${
                                (code.allowed_client_names?.length ?? 0) > 0
                                  ? code.allowed_client_names!.join(', ')
                                  : 'любой'
                              }`}
                        </p>
                        {redemptions.length > 0 && (
                          <div className="space-y-1 pt-1">
                            <p className="text-xs font-medium text-foreground">Активации</p>
                            {redemptions.map((item) => (
                              <p key={item.id} className="text-xs text-muted-foreground">
                                {item.client_name}
                                {item.node_name ? ` · ${item.node_name}` : ''}
                                {item.redeemed_at ? ` · ${formatDateTime(item.redeemed_at)}` : ''}
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="gap-1.5"
                          disabled={isRevoked || unlockCodesBusyId === code.id}
                          onClick={() => confirmRevokeUnlockCode(code)}
                        >
                          {unlockCodesBusyId === code.id ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <Trash2 size={14} />
                          )}
                          Отозвать
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {unlockCodesEnabled && availableUnlockProtocols.length === 0 && (
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <KeyRound size={18} />
              Unlock-ключи
            </CardTitle>
            <CardDescription>
              Включите хотя бы один VPN-протокол ({protocolLabel('openvpn')}, {protocolLabel('wireguard')} или{' '}
              {protocolLabel('amneziawg2')}), чтобы создавать unlock-ключи.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {!clientPortalEnabled && !unlockCodesEnabled && (
        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">Модули отключены</CardTitle>
            <CardDescription>
              Включите «Клиентский портал» и/или «Unlock-коды» в Настройки → Разделы панели.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {availableUnlockProtocols.length > 0 && (
        <UnlockCodeCreateDialog
          open={unlockCreateOpen}
          onOpenChange={setUnlockCreateOpen}
          initialProtocols={availableUnlockProtocols}
          availableProtocols={availableUnlockProtocols}
          onCreated={() => void refreshUnlockCodes()}
        />
      )}

      <ConfirmDialogHost dialogProps={dialogProps} />
    </div>
  )
}
