import { useEffect, useState } from 'react'
import { Router } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError, getSecuritySettings, updateSecuritySettings } from '@/api/client'
import RouteResultsPanel from '@/components/settings/RouteResultsPanel'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { SettingsMetaLine, SettingsToolbar } from '@/components/settings/SettingsChrome'
import Spinner from '@/components/ui/Spinner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import ToggleRow from '@/components/settings/ToggleRow'
import { useNotifications } from '@/context/NotificationContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import type { SecuritySettings } from '@/types'

export default function ConfigDeliveryTab() {
  const { success, error: notifyError } = useNotifications()
  const { isEnabled } = useFeatureModules()
  const openvpnEnabled = isEnabled('openvpn')
  const [settings, setSettings] = useState<SecuritySettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    getSecuritySettings()
      .then(setSettings)
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }, [notifyError])

  const savePublicDownload = async (enabled: boolean) => {
    setSaving(true)
    try {
      const updated = await updateSecuritySettings({ public_download_enabled: enabled })
      setSettings(updated)
      success('Настройки выдачи профилей сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <Spinner label="Загрузка настроек выдачи профилей..." className="py-12" />
  }

  if (!settings || !openvpnEnabled) return null

  return (
    <div className="space-y-4">
      <InlineProgressBar active={saving} label="Сохранение настроек..." />

      <SettingsToolbar
        title="Выдача VPN-профилей"
        meta={
          <SettingsMetaLine
            items={[
              {
                label: 'роутеры',
                value: settings.public_download_enabled ? 'без входа' : 'только из панели',
              },
            ]}
          />
        }
      />

      <p className="text-xs text-muted-foreground">
        Готовые конфиги маршрутизации для домашних роутеров. Портал и unlock-ключи — в разделе{' '}
        <Link to="/subscription" className="font-medium text-foreground underline-offset-2 hover:underline">
          Подписка
        </Link>
        .
      </p>

      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Router size={18} />
            Скачивание маршрутов
          </CardTitle>
          <CardDescription>
            Keenetic, MikroTik и TP-Link — после настройки маршрутизации
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ToggleRow
            id="public-download"
            label="Ссылка для клиента без входа в панель"
            description="Если выключено — файлы можно скачать только здесь, будучи авторизованным"
            checked={settings.public_download_enabled}
            onCheckedChange={(checked) => void savePublicDownload(checked)}
          />

          {settings.public_download_enabled && (
            <SettingsAlert variant="warning" title="Публичный доступ">
              Любой с ссылкой сможет скачать маршруты. Не публикуйте ссылку в открытых чатах.
            </SettingsAlert>
          )}

          <RouteResultsPanel showPublicLinks={settings.public_download_enabled} />
        </CardContent>
      </Card>
    </div>
  )
}
