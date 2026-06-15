import { useEffect, useState } from 'react'
import { ClipboardList, QrCode } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, getSecuritySettings, updateSecuritySettings } from '@/api/client'
import RouteResultsPanel from '@/components/settings/RouteResultsPanel'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useNotifications } from '@/context/NotificationContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import type { SecuritySettings } from '@/types'

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

  const save = async () => {
    if (!settings) return
    setSaving(true)
    try {
      const updated = await updateSecuritySettings({
        qr_download_ttl_seconds: settings.qr_download_ttl_seconds,
        qr_download_max_downloads: settings.qr_download_max_downloads,
        qr_download_pin: qrPin || undefined,
        public_download_enabled: settings.public_download_enabled,
      })
      setSettings(updated)
      success('Настройки раздачи конфигов сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <Spinner label="Загрузка настроек раздачи конфигов..." className="py-12" />
  }

  if (!settings) return null

  if (!qrDownloadsEnabled && !openvpnEnabled) {
    return null
  }

  return (
    <div className="space-y-4">
      <InlineProgressBar active={saving} label="Сохранение настроек..." />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <QrCode size={18} />
            Раздача конфигов клиентам
          </CardTitle>
          <CardDescription>
            Публичные route-файлы для роутеров и одноразовые ссылки для скачивания профилей
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {openvpnEnabled && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium">Route-файлы для роутеров</h4>
              <p className="text-sm text-muted-foreground">
                Готовые списки маршрутов для Keenetic, MikroTik и TP-Link — скачайте или откройте
                публичную ссылку для настройки роутера.
              </p>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.public_download_enabled}
                  onChange={(e) =>
                    setSettings({ ...settings, public_download_enabled: e.target.checked })
                  }
                  className="h-4 w-4 rounded border"
                />
                Разрешить публичное скачивание route-файлов без авторизации
              </label>
              <p className="text-xs text-muted-foreground">
                Публичные URL: /api/public/route-download/&#123;keenetic|mikrotik|tplink&#125;
              </p>
              <RouteResultsPanel />
            </div>
          )}

          {qrDownloadsEnabled && openvpnEnabled && <hr className="border-border" />}

          {qrDownloadsEnabled && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-sm font-medium">Одноразовые ссылки</h4>
                <Button variant="outline" size="sm" asChild>
                  <Link to="/logs?tab=qr-downloads">
                    <ClipboardList size={14} className="mr-1" />
                    Журнал QR-скачиваний
                  </Link>
                </Button>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>TTL одноразовой ссылки (сек)</Label>
                  <Input
                    type="number"
                    value={settings.qr_download_ttl_seconds}
                    onChange={(e) =>
                      setSettings({ ...settings, qr_download_ttl_seconds: Number(e.target.value) })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label>Макс. скачиваний</Label>
                  <div className="flex flex-wrap gap-4">
                    {([1, 3, 5] as const).map((n) => (
                      <label key={n} className="flex cursor-pointer items-center gap-2 text-sm">
                        <input
                          type="radio"
                          name="qr-download-max-downloads"
                          checked={settings.qr_download_max_downloads === n}
                          onChange={() => setSettings({ ...settings, qr_download_max_downloads: n })}
                          className="h-4 w-4"
                        />
                        {n}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>PIN для скачивания</Label>
                  <Input
                    type="password"
                    value={qrPin}
                    onChange={(e) => setQrPin(e.target.value)}
                    placeholder="Пусто = без PIN"
                  />
                </div>
              </div>
            </div>
          )}

          <Button onClick={save} disabled={saving}>
            {saving ? 'Сохранение...' : 'Сохранить настройки'}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
