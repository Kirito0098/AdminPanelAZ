import { useEffect, useState } from 'react'
import { ClipboardList, Download, Globe, KeyRound, Loader2, QrCode, Router, Save, Shield, Timer, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, getSecuritySettings, updateSecuritySettings } from '@/api/client'
import { getUnlockCodes, revokeUnlockCode, type UnlockCodeProtocol } from '@/api/unlockCodes'
import RouteResultsPanel from '@/components/settings/RouteResultsPanel'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { SettingsMetaLine, SettingsToolbar } from '@/components/settings/SettingsChrome'
import UnlockCodeCreateDialog from '@/components/dashboard/UnlockCodeCreateDialog'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { formatDateTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { SecuritySettings, UnlockCodeRecord } from '@/types'

const MAX_DOWNLOAD_OPTIONS = [1, 3, 5] as const
const TTL_PRESETS_MIN = [15, 60, 240] as const

function ToggleRow({
  id,
  label,
  description,
  checked,
  disabled,
  onCheckedChange,
}: {
  id: string
  label: string
  description?: string
  checked: boolean
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div
      className={cn(
        'flex items-start justify-between gap-4 rounded-xl border bg-card/50 p-4 transition-colors',
        checked && !disabled && 'border-primary/20 bg-primary/5',
        disabled && 'opacity-60',
      )}
    >
      <div className="min-w-0 space-y-1">
        <Label htmlFor={id} className={cn('font-medium', !disabled && 'cursor-pointer')}>
          {label}
        </Label>
        {description && <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
    </div>
  )
}

function formatTtlMinutes(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60))
  if (minutes < 60) return `${minutes} мин`
  const hours = Math.floor(minutes / 60)
  const rem = minutes % 60
  return rem > 0 ? `${hours} ч ${rem} мин` : `${hours} ч`
}

export default function ConfigDeliveryTab() {
  const { success, error: notifyError } = useNotifications()
  const { isEnabled } = useFeatureModules()
  const qrDownloadsEnabled = isEnabled('qr_downloads')
  const clientPortalEnabled = isEnabled('client_portal')
  const unlockCodesEnabled = isEnabled('unlock_codes')
  const openvpnEnabled = isEnabled('openvpn')
  const wireguardEnabled = isEnabled('wireguard')
  const awg2Enabled = isEnabled('awg2')
  const [settings, setSettings] = useState<SecuritySettings | null>(null)
  const [qrPin, setQrPin] = useState('')
  const [portalDomain, setPortalDomain] = useState('')
  const [unlockCodes, setUnlockCodes] = useState<UnlockCodeRecord[]>([])
  const [unlockCodesLoading, setUnlockCodesLoading] = useState(false)
  const [unlockCodesBusyId, setUnlockCodesBusyId] = useState<number | null>(null)
  const [unlockCreateOpen, setUnlockCreateOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    getSecuritySettings()
      .then((data) => {
        setSettings(data)
        setPortalDomain(data.portal_domain || '')
      })
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }, [notifyError])

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

  const persistSettings = async (snapshot: {
    settings: SecuritySettings
    qrPin: string
    portalDomain: string
  }) => {
    setSaving(true)
    try {
      const updated = await updateSecuritySettings({
        qr_download_ttl_seconds: snapshot.settings.qr_download_ttl_seconds,
        qr_download_max_downloads: snapshot.settings.qr_download_max_downloads,
        qr_download_pin: snapshot.qrPin || undefined,
        public_download_enabled: snapshot.settings.public_download_enabled,
        portal_domain: snapshot.portalDomain.trim(),
      })
      setSettings(updated)
      setPortalDomain(updated.portal_domain || '')
      if (snapshot.qrPin) setQrPin('')
      success('Настройки выдачи профилей сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const save = () => {
    if (!settings) return
    void persistSettings({ settings, qrPin, portalDomain })
  }

  const saveWithPatch = (patch: Partial<SecuritySettings>) => {
    if (!settings) return
    const next = { ...settings, ...patch }
    setSettings(next)
    void persistSettings({ settings: next, qrPin: '', portalDomain })
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
      success(`Код «${code.code}» отозван`)
      await refreshUnlockCodes()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отзыва unlock-ключа')
    } finally {
      setUnlockCodesBusyId(null)
    }
  }

  if (loading) {
    return <Spinner label="Загрузка настроек выдачи профилей..." className="py-12" />
  }

  if (!settings) return null

  if (!qrDownloadsEnabled && !openvpnEnabled && !clientPortalEnabled && !unlockCodesEnabled) {
    return null
  }

  const bothSections = qrDownloadsEnabled && openvpnEnabled
  const ttlMinutes = Math.max(1, Math.round(settings.qr_download_ttl_seconds / 60))
  const portalPreviewHost = portalDomain.trim().replace(/^https?:\/\//i, '').split('/')[0] || 'sub.example.com'
  const availableUnlockProtocols: UnlockCodeProtocol[] = []
  if (openvpnEnabled) availableUnlockProtocols.push('openvpn')
  if (wireguardEnabled) availableUnlockProtocols.push('wireguard')
  if (awg2Enabled) availableUnlockProtocols.push('amneziawg2')

  return (
    <div className="space-y-4">
      <InlineProgressBar active={saving} label="Сохранение настроек..." />

      <SettingsToolbar
        title="Выдача VPN-профилей"
        meta={
          <SettingsMetaLine
            items={[
              ...(openvpnEnabled
                ? [{ label: 'роутеры', value: settings.public_download_enabled ? 'без входа' : 'только из панели' }]
                : []),
              ...(qrDownloadsEnabled
                ? [
                    { label: 'срок ссылки QR', value: formatTtlMinutes(settings.qr_download_ttl_seconds) },
                    { label: 'лимит скачиваний', value: `до ${settings.qr_download_max_downloads} раз` },
                  ]
                : []),
            ]}
          />
        }
      />

      <p className="text-xs text-muted-foreground">
        {bothSections
          ? 'Файлы маршрутов для роутеров и временные QR-ссылки на профили'
          : openvpnEnabled
            ? 'Готовые конфиги маршрутизации для домашних роутеров'
            : 'Временные ссылки и QR-коды для передачи профиля клиенту'}
      </p>

      {clientPortalEnabled && (
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Globe size={18} />
              Клиентский портал
            </CardTitle>
            <CardDescription>
              Постоянные ссылки на отдельном поддомене: страница установки, OpenVPN import и скачивание
              профилей. DNS и TLS настройте сами (прокси на эту панель).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="portal-domain">Поддомен / хост портала</Label>
              <Input
                id="portal-domain"
                value={portalDomain}
                onChange={(e) => setPortalDomain(e.target.value)}
                placeholder="sub.example.com"
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">
                Без схемы. Пример ссылки:{' '}
                <code className="rounded bg-muted px-1 py-0.5">
                  https://{portalPreviewHost}/p/…
                </code>
                . Не используйте домен самой панели. При заданном хосте одноразовые QR-ссылки тоже
                строятся с него.
              </p>
            </div>
            <div className="flex justify-end border-t pt-4">
              <Button onClick={save} disabled={saving} className="gap-1.5">
                <Save size={16} />
                {saving ? 'Сохранение...' : 'Сохранить портал'}
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
                Создание и отзыв ключей продления для клиентов
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
                  const protocolList = code.protocols.join(', ')
                  return (
                    <div
                      key={code.id}
                      className="flex flex-col gap-3 rounded-xl border bg-card/60 p-3 sm:flex-row sm:items-start sm:justify-between"
                    >
                      <div className="min-w-0 space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="break-all font-mono text-sm font-semibold">{code.code}</p>
                          <Badge variant={code.mode === 'multi' ? 'default' : 'secondary'}>
                            {code.mode === 'multi' ? 'multi' : 'single'}
                          </Badge>
                          {isRevoked && <Badge variant="destructive">Отозван</Badge>}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {code.grant_days} дн. · до {code.max_redemptions} активаций
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Протоколы: {protocolList || '—'} · создан {formatDateTime(code.created_at)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Истекает: {formatDateTime(code.code_expires_at)} · активаций: {code.redemption_count ?? 0}
                        </p>
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

      <div
        className={cn(
          'grid gap-4',
          bothSections ? 'md:grid-cols-2 md:items-stretch' : undefined,
        )}
      >
        {openvpnEnabled && (
            <Card className="flex h-full flex-col shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Router size={18} />
                  Скачивание маршрутов
                </CardTitle>
                <CardDescription>
                  Keenetic, MikroTik и TP-Link — после настройки маршрутизации
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col space-y-4">
                <ToggleRow
                  id="public-download"
                  label="Ссылка для клиента без входа в панель"
                  description="Если выключено — файлы можно скачать только здесь, будучи авторизованным"
                  checked={settings.public_download_enabled}
                  onCheckedChange={(checked) => saveWithPatch({ public_download_enabled: checked })}
                />

                {settings.public_download_enabled && (
                  <SettingsAlert variant="warning" title="Публичный доступ">
                    Любой с ссылкой сможет скачать маршруты. Не публикуйте ссылку в открытых чатах.
                  </SettingsAlert>
                )}

                <RouteResultsPanel showPublicLinks={settings.public_download_enabled} />
              </CardContent>
            </Card>
        )}

        {qrDownloadsEnabled && (
            <Card className="flex h-full flex-col shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <QrCode size={18} />
                    {bothSections ? 'QR-ссылки' : 'Ссылки и QR-коды'}
                  </CardTitle>
                  <CardDescription className="mt-1.5">
                    Срок, лимит скачиваний и опциональный PIN
                  </CardDescription>
                </div>
                <Button variant="outline" size="sm" className="shrink-0 gap-1.5" asChild>
                  <Link to="/logs?tab=qr-downloads">
                    <ClipboardList size={14} />
                    Журнал
                  </Link>
                </Button>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col space-y-4">
                <div className="rounded-xl border bg-muted/20 p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <Timer size={14} className="text-muted-foreground" />
                    <Label className="text-sm">Срок действия ссылки</Label>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {TTL_PRESETS_MIN.map((min) => (
                      <button
                        key={min}
                        type="button"
                        onClick={() => setSettings({ ...settings, qr_download_ttl_seconds: min * 60 })}
                        className={cn(
                          'rounded-lg border px-3 py-2 text-sm font-medium transition-all',
                          ttlMinutes === min
                            ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
                            : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                        )}
                      >
                        {min < 60 ? `${min} мин` : `${min / 60} ч`}
                      </button>
                    ))}
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <Input
                      type="number"
                      min={1}
                      max={1440}
                      className="h-9 w-24"
                      value={ttlMinutes}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          qr_download_ttl_seconds: Math.max(60, Number(e.target.value) * 60),
                        })
                      }
                    />
                    <span className="text-sm text-muted-foreground">минут</span>
                  </div>
                </div>

                <div className="rounded-xl border bg-muted/20 p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <Download size={14} className="text-muted-foreground" />
                    <Label className="text-sm">Сколько раз можно скачать по одной ссылке</Label>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {MAX_DOWNLOAD_OPTIONS.map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setSettings({ ...settings, qr_download_max_downloads: n })}
                        className={cn(
                          'rounded-lg border px-4 py-2 text-sm font-medium transition-all',
                          settings.qr_download_max_downloads === n
                            ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
                            : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                        )}
                      >
                        {n} {n === 1 ? 'раз' : 'раза'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border bg-muted/20 p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <Shield size={14} className="text-muted-foreground" />
                    <Label htmlFor="qr-pin" className="text-sm">
                      PIN-код (необязательно)
                    </Label>
                    {settings.qr_download_pin_set && (
                      <Badge variant="secondary" className="text-[10px]">
                        задан
                      </Badge>
                    )}
                  </div>
                  <Input
                    id="qr-pin"
                    type="password"
                    value={qrPin}
                    onChange={(e) => setQrPin(e.target.value)}
                    placeholder={settings.qr_download_pin_set ? '••••••••' : 'Без PIN — ссылка откроется сразу'}
                  />
                  <p className="mt-2 text-xs text-muted-foreground">
                    Клиент введёт PIN при открытии ссылки. Оставьте пустым, чтобы не менять текущий PIN.
                  </p>
                </div>

                <div className="mt-auto flex justify-end border-t pt-4">
                  <Button onClick={save} disabled={saving} className="gap-1.5">
                    <Save size={16} />
                    {saving ? 'Сохранение...' : 'Сохранить'}
                  </Button>
                </div>
              </CardContent>
            </Card>
        )}
        </div>

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
