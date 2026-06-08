import { useEffect, useState } from 'react'
import { Ban, Clock, Shield, ShieldOff } from 'lucide-react'
import {
  ApiError,
  addTempWhitelist,
  getClientIp,
  getScannerBans,
  getSecuritySettings,
  removeTempWhitelist,
  unbanScannerIp,
  updateSecuritySettings,
} from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import EmptyState from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useNotifications } from '@/context/NotificationContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import type { ScannerBan, SecuritySettings } from '@/types'

export default function SecurityTab() {
  const { success, error: notifyError } = useNotifications()
  const { isEnabled } = useFeatureModules()
  const qrDownloadsEnabled = isEnabled('qr_downloads')
  const openvpnEnabled = isEnabled('openvpn')
  const [settings, setSettings] = useState<SecuritySettings | null>(null)
  const [allowedIps, setAllowedIps] = useState('')
  const [qrPin, setQrPin] = useState('')
  const [bans, setBans] = useState<ScannerBan[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [clientIp, setClientIp] = useState<string | null>(null)
  const [tempHours, setTempHours] = useState<1 | 12 | 24>(1)
  const [tempIpInput, setTempIpInput] = useState('')
  const [addingTemp, setAddingTemp] = useState(false)
  const [removingTempIp, setRemovingTempIp] = useState<string | null>(null)

  const load = async () => {
    try {
      const s = await getSecuritySettings()
      setSettings(s)
      setAllowedIps(s.allowed_ips.join(', '))
      const [b, ipInfo] = await Promise.all([getScannerBans(), getClientIp()])
      setBans(b.active_bans || [])
      setClientIp(ipInfo.client_ip)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    }
  }

  useEffect(() => {
    setLoading(true)
    load().finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true)
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
        public_download_enabled: settings?.public_download_enabled,
      })
      setSettings(updated)
      success('Настройки безопасности сохранены')
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
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

  const handleAddTempWhitelist = async (ip?: string) => {
    const targetIp = (ip ?? (tempIpInput.trim() || clientIp))?.trim()
    if (!targetIp) {
      notifyError('Не удалось определить IP-адрес')
      return
    }
    setAddingTemp(true)
    try {
      const updated = await addTempWhitelist(targetIp, tempHours)
      setSettings(updated)
      setTempIpInput('')
      success(`IP ${targetIp} добавлен на ${tempHours} ч.`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка добавления IP')
    } finally {
      setAddingTemp(false)
    }
  }

  const handleRemoveTempWhitelist = async (ip: string) => {
    setRemovingTempIp(ip)
    try {
      const updated = await removeTempWhitelist(ip)
      setSettings(updated)
      success(`IP ${ip} удалён из временного whitelist`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления IP')
    } finally {
      setRemovingTempIp(null)
    }
  }

  const ipRestrictionActive = settings?.ip_restriction_enabled ?? false

  if (loading) {
    return <Spinner label="Загрузка настроек безопасности..." className="py-12" />
  }

  if (!settings) return null

  return (
    <div className="space-y-4">
      <InlineProgressBar active={saving} label="Сохранение настроек..." />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield size={18} />
            Доступ и защита
          </CardTitle>
          <CardDescription>IP whitelist, блокировка сканеров (iptables/ipset), одноразовые ссылки</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-4">
            <h4 className="text-sm font-medium">Ограничение по IP</h4>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.ip_restriction_enabled}
                onChange={(e) => setSettings({ ...settings, ip_restriction_enabled: e.target.checked })}
                className="h-4 w-4 rounded border"
              />
              Ограничение доступа по IP
            </label>
            <div className="space-y-2">
              <Label>Разрешённые IP/CIDR (через запятую)</Label>
              <Input
                value={allowedIps}
                onChange={(e) => setAllowedIps(e.target.value)}
                placeholder="192.168.1.0/24, 10.0.0.1"
              />
              <p className="text-xs text-muted-foreground">Оставьте пустым при выключенном ограничении</p>
            </div>

            <div className={`space-y-4 rounded-md border p-4 ${!ipRestrictionActive ? 'opacity-60' : ''}`}>
              <h4 className="flex items-center gap-2 text-sm font-medium">
                <Clock size={16} />
                Временный whitelist
              </h4>
              <p className="text-xs text-muted-foreground">
                Временно разрешить доступ с IP, не добавляя его в постоянный список.
                {!ipRestrictionActive && ' Доступно при включённом ограничении по IP.'}
              </p>

              <fieldset disabled={!ipRestrictionActive || addingTemp} className="space-y-4">
                <div className="space-y-2">
                  <Label>Срок доступа</Label>
                  <div className="flex flex-wrap gap-4">
                    {([1, 12, 24] as const).map((h) => (
                      <label key={h} className="flex cursor-pointer items-center gap-2 text-sm">
                        <input
                          type="radio"
                          name="temp-whitelist-hours"
                          checked={tempHours === h}
                          onChange={() => setTempHours(h)}
                          className="h-4 w-4"
                        />
                        {h} ч.
                      </label>
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>IP-адрес (необязательно)</Label>
                  <Input
                    value={tempIpInput}
                    onChange={(e) => setTempIpInput(e.target.value)}
                    placeholder={clientIp ? `Пусто = ${clientIp}` : '192.168.1.100'}
                    className="font-mono"
                  />
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!clientIp}
                    onClick={() => handleAddTempWhitelist(clientIp ?? undefined)}
                  >
                    {addingTemp ? 'Добавление...' : 'Добавить текущий IP'}
                  </Button>
                  <Button
                    type="button"
                    disabled={!tempIpInput.trim()}
                    onClick={() => handleAddTempWhitelist()}
                  >
                    Добавить указанный IP
                  </Button>
                </div>
              </fieldset>

              {settings.temp_whitelist.length > 0 && (
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>IP</TableHead>
                        <TableHead>Истекает</TableHead>
                        <TableHead>Срок (ч)</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {settings.temp_whitelist.map((entry) => (
                        <TableRow key={entry.ip}>
                          <TableCell className="font-mono">{entry.ip}</TableCell>
                          <TableCell>
                            {new Date(entry.expires_at).toLocaleString('ru-RU')}
                          </TableCell>
                          <TableCell>{entry.hours}</TableCell>
                          <TableCell>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={!ipRestrictionActive || removingTempIp === entry.ip}
                              onClick={() => handleRemoveTempWhitelist(entry.ip)}
                            >
                              {removingTempIp === entry.ip ? 'Удаление...' : 'Удалить'}
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          </div>

          <Separator />

          <div className="space-y-4">
            <h4 className="text-sm font-medium">Защита от сканеров</h4>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.block_scanners}
                onChange={(e) => setSettings({ ...settings, block_scanners: e.target.checked })}
                className="h-4 w-4 rounded border"
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
            </div>
          </div>

          <Separator />

          {openvpnEnabled && (
            <div className="space-y-4">
              <h4 className="text-sm font-medium">Публичные route-файлы</h4>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.public_download_enabled}
                  onChange={(e) =>
                    setSettings({ ...settings, public_download_enabled: e.target.checked })
                  }
                  className="h-4 w-4 rounded border"
                />
                Разрешить публичное скачивание route-файлов (Keenetic, MikroTik, TP-Link)
              </label>
              <p className="text-xs text-muted-foreground">
                Ссылки: /api/public/route-download/&#123;keenetic|mikrotik|tplink&#125;
              </p>
            </div>
          )}

          {qrDownloadsEnabled && (
          <div className="space-y-4">
            <h4 className="text-sm font-medium">Одноразовые ссылки</h4>
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

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Ban size={18} />
            Активные баны сканеров
          </CardTitle>
          <CardDescription>IP-адреса, временно заблокированные системой защиты</CardDescription>
        </CardHeader>
        <CardContent>
          {bans.length === 0 ? (
            <EmptyState
              icon={ShieldOff}
              title="Активных банов нет"
              description="Заблокированные сканеры появятся здесь автоматически"
              className="py-6"
            />
          ) : (
            <div className="overflow-x-auto rounded-md border">
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
                      <TableCell>
                        {b.strikes}
                        {b.long_term ? ' (долгий)' : ''}
                      </TableCell>
                      <TableCell>
                        <Button size="sm" variant="outline" onClick={() => handleUnban(b.ip)}>
                          Разблокировать
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
