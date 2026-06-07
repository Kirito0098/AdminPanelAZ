import { useEffect, useState } from 'react'
import { Shield } from 'lucide-react'
import { ApiError, getSecuritySettings, updateSecuritySettings } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'
import type { SecuritySettings } from '@/types'

export default function SecurityTab() {
  const { success, error: notifyError } = useNotifications()
  const [settings, setSettings] = useState<SecuritySettings | null>(null)
  const [allowedIps, setAllowedIps] = useState('')
  const [qrPin, setQrPin] = useState('')

  useEffect(() => {
    getSecuritySettings()
      .then((s) => {
        setSettings(s)
        setAllowedIps(s.allowed_ips.join(', '))
      })
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки'))
  }, [])

  const save = async () => {
    try {
      const updated = await updateSecuritySettings({
        ip_restriction_enabled: settings?.ip_restriction_enabled,
        allowed_ips: allowedIps.split(',').map((s) => s.trim()).filter(Boolean),
        block_scanners: settings?.block_scanners,
        scanner_max_attempts: settings?.scanner_max_attempts,
        scanner_ban_seconds: settings?.scanner_ban_seconds,
        qr_download_ttl_seconds: settings?.qr_download_ttl_seconds,
        qr_download_max_downloads: settings?.qr_download_max_downloads,
        qr_download_pin: qrPin || undefined,
      })
      setSettings(updated)
      success('Настройки безопасности сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    }
  }

  if (!settings) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Shield size={18} />
          Безопасность
        </CardTitle>
        <CardDescription>IP whitelist, блокировка сканеров, одноразовые ссылки</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.ip_restriction_enabled}
            onChange={(e) => setSettings({ ...settings, ip_restriction_enabled: e.target.checked })}
          />
          Ограничение доступа по IP
        </label>
        <div className="space-y-2">
          <Label>Разрешённые IP/CIDR (через запятую)</Label>
          <Input value={allowedIps} onChange={(e) => setAllowedIps(e.target.value)} placeholder="192.168.1.0/24, 10.0.0.1" />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.block_scanners}
            onChange={(e) => setSettings({ ...settings, block_scanners: e.target.checked })}
          />
          Блокировать сканеры
        </label>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>TTL одноразовой ссылки (сек)</Label>
            <Input
              type="number"
              value={settings.qr_download_ttl_seconds}
              onChange={(e) => setSettings({ ...settings, qr_download_ttl_seconds: Number(e.target.value) })}
            />
          </div>
          <div className="space-y-2">
            <Label>PIN для скачивания (пусто = без PIN)</Label>
            <Input type="password" value={qrPin} onChange={(e) => setQrPin(e.target.value)} placeholder="Не менять" />
          </div>
        </div>
        <Button onClick={save}>Сохранить</Button>
      </CardContent>
    </Card>
  )
}
