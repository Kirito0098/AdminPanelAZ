import { useCallback, useEffect, useState } from 'react'
import { Globe, KeyRound, Loader2, Rocket, Save, Ticket, Trash2 } from 'lucide-react'
import {
  ApiError,
  getPortalPublishStatus,
  getSecuritySettings,
  publishPortalDomain,
  updateSecuritySettings,
} from '@/api/client'
import UnlockCodeCreateDialog from '@/components/dashboard/UnlockCodeCreateDialog'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { formatDateTime } from '@/lib/datetime'
import {
  isUnlockCodeExhausted,
  unlockCodeRedeemedCount,
  unlockCodeStatusLabel,
} from '@/lib/unlockCodeStatus'
import { cn } from '@/lib/utils'
import type { PortalPublishStatus, UnlockCodeRecord } from '@/types'
import { getUnlockCodes, revokeUnlockCode, type UnlockCodeProtocol } from '@/api/unlockCodes'

export default function SubscriptionPage() {
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()
  const { isEnabled } = useFeatureModules()
  const clientPortalEnabled = isEnabled('client_portal')
  const unlockCodesEnabled = isEnabled('unlock_codes')
  const openvpnEnabled = isEnabled('openvpn')
  const wireguardEnabled = isEnabled('wireguard') || isEnabled('amneziawg')
  const awg2Enabled = isEnabled('awg2')

  const [portalDomain, setPortalDomain] = useState('')
  const [portalStatus, setPortalStatus] = useState<PortalPublishStatus | null>(null)
  const [loading, setLoading] = useState(clientPortalEnabled)
  const [saving, setSaving] = useState(false)
  const [provisioning, setProvisioning] = useState(false)
  const [unlockCodes, setUnlockCodes] = useState<UnlockCodeRecord[]>([])
  const [unlockCodesLoading, setUnlockCodesLoading] = useState(false)
  const [unlockCodesBusyId, setUnlockCodesBusyId] = useState<number | null>(null)
  const [unlockCreateOpen, setUnlockCreateOpen] = useState(false)

  const refreshPortalStatus = useCallback(async () => {
    if (!clientPortalEnabled) {
      setPortalStatus(null)
      return
    }
    try {
      setPortalStatus(await getPortalPublishStatus())
    } catch {
      setPortalStatus(null)
    }
  }, [clientPortalEnabled])

  useEffect(() => {
    if (!clientPortalEnabled) {
      setPortalDomain('')
      setPortalStatus(null)
      setLoading(false)
      return
    }
    setLoading(true)
    Promise.all([getSecuritySettings(), getPortalPublishStatus()])
      .then(([data, status]) => {
        setPortalDomain(data.portal_domain || status.suggested_portal_domain || '')
        setPortalStatus(status)
      })
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
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

  const portalPreviewHost =
    portalDomain.trim().replace(/^https?:\/\//i, '').split('/')[0] ||
    portalStatus?.suggested_portal_domain ||
    'portal.example.com'

  const savePortal = async () => {
    setSaving(true)
    try {
      const updated = await updateSecuritySettings({
        portal_domain: portalDomain.trim(),
      })
      setPortalDomain(updated.portal_domain || '')
      success('Настройки портала сохранены')
      await refreshPortalStatus()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const provisionPortal = async () => {
    const host = portalDomain.trim()
    if (!host) {
      notifyError('Укажите хост портала')
      return
    }
    setProvisioning(true)
    try {
      const resp = await publishPortalDomain({ portal_domain: host, save_domain: true })
      trackBackgroundTask(resp.task_id, {
        onComplete: () => {
          setProvisioning(false)
          success(resp.message || 'Портал настроен')
          void refreshPortalStatus()
        },
        onError: (_task, message) => {
          setProvisioning(false)
          notifyError(message || 'Не удалось настроить портал')
        },
      })
    } catch (err) {
      setProvisioning(false)
      notifyError(err instanceof ApiError ? err.message : 'Ошибка запуска настройки')
    }
  }

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

  if (loading && clientPortalEnabled) {
    return <Spinner label="Загрузка…" className="py-12" />
  }

  return (
    <div className="space-y-6">
      <PageSectionHeader
        icon={Ticket}
        title="Подписка"
        description="Клиентский портал и unlock-ключи продления доступа"
      />

      <InlineProgressBar
        active={saving || provisioning}
        label={provisioning ? 'Настройка портала…' : 'Сохранение настроек...'}
      />

      {clientPortalEnabled && (
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Globe size={18} />
              Клиентский портал
            </CardTitle>
            <CardDescription>
              Постоянные ссылки на отдельном поддомене (всегда с корня хоста, без подпути панели
              вроде /panel). Панель сама настроит nginx/сертификат под текущий способ публикации
              (Настройки → Адрес сайта и HTTPS). DNS-запись нужно создать у регистратора.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="portal-domain">Поддомен / хост портала</Label>
              <Input
                id="portal-domain"
                value={portalDomain}
                onChange={(e) => setPortalDomain(e.target.value)}
                placeholder={portalStatus?.suggested_portal_domain || 'portal.example.com'}
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">
                Без схемы. Пример:{' '}
                <code className="rounded bg-muted px-1 py-0.5">https://{portalPreviewHost}/p/…</code>
                . Не используйте домен самой панели
                {portalStatus?.panel_domain ? ` (${portalStatus.panel_domain})` : ''}.
                {portalStatus?.suggested_portal_domain &&
                portalDomain.trim() !== portalStatus.suggested_portal_domain ? (
                  <>
                    {' '}
                    <button
                      type="button"
                      className="text-primary underline-offset-2 hover:underline"
                      onClick={() => setPortalDomain(portalStatus.suggested_portal_domain)}
                    >
                      Подставить {portalStatus.suggested_portal_domain}
                    </button>
                  </>
                ) : null}
              </p>
            </div>

            {portalStatus && (
              <div className="space-y-2 rounded-xl border bg-muted/20 p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-muted-foreground">Статус:</span>
                  {portalStatus.portal_ready ? (
                    <Badge variant="success">Готов</Badge>
                  ) : (
                    <Badge variant="warning">Нужна настройка</Badge>
                  )}
                  {portalStatus.active_publish_mode ? (
                    <Badge variant="outline">{portalStatus.active_publish_mode}</Badge>
                  ) : null}
                </div>
                {portalStatus.dns_hint ? (
                  <p className="text-xs text-muted-foreground">{portalStatus.dns_hint}</p>
                ) : null}
                {portalStatus.warnings.map((w) => (
                  <p key={w} className="text-xs text-amber-700 dark:text-amber-400">
                    {w}
                  </p>
                ))}
                {portalStatus.portal_access_url ? (
                  <p className="text-xs text-muted-foreground">
                    URL:{' '}
                    <code className="rounded bg-muted px-1 py-0.5">
                      {portalStatus.portal_access_url}p/…
                    </code>
                  </p>
                ) : null}
              </div>
            )}

            <div className="flex flex-col-reverse gap-2 border-t pt-4 sm:flex-row sm:justify-end">
              <Button onClick={() => void savePortal()} disabled={saving || provisioning} variant="outline" className="gap-1.5">
                <Save size={16} />
                {saving ? 'Сохранение...' : 'Сохранить хост'}
              </Button>
              <Button
                onClick={() => void provisionPortal()}
                disabled={saving || provisioning || !portalDomain.trim()}
                className="gap-1.5"
              >
                <Rocket size={16} />
                {provisioning ? 'Настройка…' : 'Настроить под текущую публикацию'}
              </Button>
            </div>
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
                  const protocolList = code.protocols.join(', ')
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
                          {(code.allowed_client_names?.length ?? 0) > 0
                            ? 'Профиль'
                            : `Протоколы: ${protocolList || '—'}`}{' '}
                          · создан {formatDateTime(code.created_at)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Истекает: {formatDateTime(code.code_expires_at)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Клиенты:{' '}
                          {(code.allowed_client_names?.length ?? 0) > 0
                            ? code.allowed_client_names!.join(', ')
                            : 'любой'}
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
                          onClick={() => void handleRevokeUnlockCode(code)}
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
              Включите хотя бы один VPN-протокол (OpenVPN, WireGuard / AmneziaWG или AmneziaWG 2.0),
              чтобы создавать unlock-ключи.
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
    </div>
  )
}
