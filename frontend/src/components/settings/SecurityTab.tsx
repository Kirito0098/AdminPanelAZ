import { useEffect, useState } from 'react'
import { Ban, Shield } from 'lucide-react'
import {
  ApiError,
  getScannerBans,
  getSecuritySettings,
  unbanScannerIp,
  updateSecuritySettings,
} from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useNotifications } from '@/context/NotificationContext'
import type { ScannerBan, SecuritySettings } from '@/types'

export default function SecurityTab() {
  const { success, error: notifyError } = useNotifications()
  const [settings, setSettings] = useState<SecuritySettings | null>(null)
  const [allowedIps, setAllowedIps] = useState('')
  const [qrPin, setQrPin] = useState('')
  const [bans, setBans] = useState<ScannerBan[]>([])

  const load = async () => {
    try {
      const s = await getSecuritySettings()
      setSettings(s)
      setAllowedIps(s.allowed_ips.join(', '))
      const b = await getScannerBans()
      setBans(b.active_bans || [])
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    }
  }

  useEffect(() => {
    load()
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
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    }
  }

  const handleUnban = async (ip: string) => {
    try {
      await unbanScannerIp(ip)
      success(`IP ${ip} разблокирован`)
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка разблокировки')
    }
  }

  if (!settings) return null

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield size={18} />
            Безопасность
          </CardTitle>
          <CardDescription>IP whitelist, блокировка сканеров (iptables/ipset), одноразовые ссылки</CardDescription>
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
            Блокировать сканеры (iptables/ipset при root)
          </label>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Макс. попыток</Label>
              <Input
                type="number"
                value={settings.scanner_max_attempts}
                onChange={(e) => setSettings({ ...settings, scanner_max_attempts: Number(e.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label>Бан (сек)</Label>
              <Input
                type="number"
                value={settings.scanner_ban_seconds}
                onChange={(e) => setSettings({ ...settings, scanner_ban_seconds: Number(e.target.value) })}
              />
            </div>
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

      {bans.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Ban size={18} />
              Активные баны сканеров
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>IP</TableHead>
                  <TableHead>Осталось (сек)</TableHead>
                  <TableHead>Удары</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {bans.map((b) => (
                  <TableRow key={b.ip}>
                    <TableCell className="font-mono">{b.ip}</TableCell>
                    <TableCell>{b.remaining_seconds}</TableCell>
                    <TableCell>{b.strikes}{b.long_term ? ' (долгий)' : ''}</TableCell>
                    <TableCell>
                      <Button size="sm" variant="outline" onClick={() => handleUnban(b.ip)}>
                        Разблокировать
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
