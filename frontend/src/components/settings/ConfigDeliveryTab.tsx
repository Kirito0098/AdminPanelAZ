import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ClipboardList, Download, QrCode, Router, Save, Shield, Timer } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, getSecuritySettings, updateSecuritySettings } from '@/api/client'
import RouteResultsPanel from '@/components/settings/RouteResultsPanel'
import SettingsAlert from '@/components/settings/SettingsAlert'
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
import { cn } from '@/lib/utils'
import type { SecuritySettings } from '@/types'

const MAX_DOWNLOAD_OPTIONS = [1, 3, 5] as const
const TTL_PRESETS_MIN = [15, 60, 240] as const

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="md:col-span-2">
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

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

function MetricPill({
  icon: Icon,
  label,
  value,
  tone = 'default',
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: 'default' | 'success' | 'warning' | 'muted'
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card/80 p-3 shadow-sm backdrop-blur-sm">
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          tone === 'success' && 'bg-primary/15 text-primary',
          tone === 'warning' && 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
          tone === 'muted' && 'bg-muted text-muted-foreground',
          tone === 'default' && 'bg-muted/80 text-foreground',
        )}
      >
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-semibold">{value}</p>
      </div>
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
  const openvpnEnabled = isEnabled('openvpn')
  const [settings, setSettings] = useState<SecuritySettings | null>(null)
  const [qrPin, setQrPin] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    getSecuritySettings()
      .then(setSettings)
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }, [notifyError])

  const persistSettings = async (snapshot: { settings: SecuritySettings; qrPin: string }) => {
    setSaving(true)
    try {
      const updated = await updateSecuritySettings({
        qr_download_ttl_seconds: snapshot.settings.qr_download_ttl_seconds,
        qr_download_max_downloads: snapshot.settings.qr_download_max_downloads,
        qr_download_pin: snapshot.qrPin || undefined,
        public_download_enabled: snapshot.settings.public_download_enabled,
      })
      setSettings(updated)
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
    void persistSettings({ settings, qrPin })
  }

  const saveWithPatch = (patch: Partial<SecuritySettings>) => {
    if (!settings) return
    const next = { ...settings, ...patch }
    setSettings(next)
    void persistSettings({ settings: next, qrPin: '' })
  }

  if (loading) {
    return <Spinner label="Загрузка настроек выдачи профилей..." className="py-12" />
  }

  if (!settings) return null

  if (!qrDownloadsEnabled && !openvpnEnabled) {
    return null
  }

  const bothSections = qrDownloadsEnabled && openvpnEnabled
  const ttlMinutes = Math.max(1, Math.round(settings.qr_download_ttl_seconds / 60))

  return (
    <div className="space-y-4">
      <InlineProgressBar active={saving} label="Сохранение настроек..." />

      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 md:col-span-2">
          <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-2xl" />
          <div
            className={cn(
              'relative grid gap-3',
              openvpnEnabled && qrDownloadsEnabled
                ? 'sm:grid-cols-2 lg:grid-cols-3'
                : 'sm:grid-cols-2',
            )}
          >
            {openvpnEnabled && (
              <MetricPill
                icon={Download}
                label="Роутеры"
                value={settings.public_download_enabled ? 'Без входа' : 'Только из панели'}
                tone={settings.public_download_enabled ? 'warning' : 'muted'}
              />
            )}
            {qrDownloadsEnabled && (
              <>
                <MetricPill
                  icon={Timer}
                  label="Срок ссылки QR"
                  value={formatTtlMinutes(settings.qr_download_ttl_seconds)}
                  tone="success"
                />
                <MetricPill
                  icon={QrCode}
                  label="Лимит скачиваний"
                  value={`до ${settings.qr_download_max_downloads} раз`}
                  tone="default"
                />
              </>
            )}
          </div>
        </div>

        {(openvpnEnabled || qrDownloadsEnabled) && (
          <SectionHeading
            title="Выдача VPN-профилей"
            description={
              bothSections
                ? 'Файлы маршрутов для роутеров и временные QR-ссылки на профили'
                : openvpnEnabled
                  ? 'Готовые конфиги маршрутизации для домашних роутеров'
                  : 'Временные ссылки и QR-коды для передачи профиля клиенту'
            }
          />
        )}

        <div
          className={cn(
            'grid gap-4',
            bothSections ? 'md:col-span-2 md:grid-cols-2 md:items-stretch' : 'md:col-span-2',
          )}
        >
        {openvpnEnabled && (
            <Card className="flex h-full flex-col overflow-hidden shadow-sm">
              <div className="h-1 bg-gradient-to-r from-sky-500/70 to-sky-500/15" />
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
            <Card className="flex h-full flex-col overflow-hidden shadow-sm">
              <div className="h-1 bg-gradient-to-r from-violet-500/70 to-violet-500/15" />
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
      </div>
    </div>
  )
}
