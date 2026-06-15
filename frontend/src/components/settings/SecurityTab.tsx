import { useEffect, useState } from 'react'
import { Ban, Clock, Shield, ShieldOff } from 'lucide-react'
import {
  ApiError,
  addTempWhitelist,
  clearScannerBans,
  getActiveWebSessions,
  getClientIp,
  getEventWebhookSettings,
  getAuditStreamSettings,
  getScannerBans,
  getSecuritySettings,
  removeTempWhitelist,
  revokeActiveWebSession,
  unbanScannerIp,
  updateEventWebhookSettings,
  updateAuditStreamSettings,
  testAuditStream,
  updateSecuritySettings,
} from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import type { ActiveWebSession, AuditStreamSettings, EventWebhookSettings, ScannerBan, SecuritySettings } from '@/types'

export default function SecurityTab() {
  const { success, error: notifyError } = useNotifications()
  const [settings, setSettings] = useState<SecuritySettings | null>(null)
  const [allowedIps, setAllowedIps] = useState('')
  const [bans, setBans] = useState<ScannerBan[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [clientIp, setClientIp] = useState<string | null>(null)
  const [tempHours, setTempHours] = useState<1 | 12 | 24>(1)
  const [tempIpInput, setTempIpInput] = useState('')
  const [addingTemp, setAddingTemp] = useState(false)
  const [removingTempIp, setRemovingTempIp] = useState<string | null>(null)
  const [clearingBans, setClearingBans] = useState(false)
  const [sessions, setSessions] = useState<ActiveWebSession[]>([])
  const [revokingSession, setRevokingSession] = useState<string | null>(null)
  const [webhookSettings, setWebhookSettings] = useState<EventWebhookSettings | null>(null)
  const [webhookUrl, setWebhookUrl] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [savingWebhooks, setSavingWebhooks] = useState(false)
  const [auditStream, setAuditStream] = useState<AuditStreamSettings | null>(null)
  const [auditHttpUrl, setAuditHttpUrl] = useState('')
  const [auditSecret, setAuditSecret] = useState('')
  const [auditSyslogHost, setAuditSyslogHost] = useState('')
  const [savingAuditStream, setSavingAuditStream] = useState(false)
  const [testingAuditStream, setTestingAuditStream] = useState(false)

  const load = async () => {
    try {
      const s = await getSecuritySettings()
      setSettings(s)
      setAllowedIps(s.allowed_ips.join(', '))
      const [b, ipInfo, activeSessions, hooks, audit] = await Promise.all([
        getScannerBans(),
        getClientIp(),
        getActiveWebSessions().catch(() => [] as ActiveWebSession[]),
        getEventWebhookSettings().catch(() => null),
        getAuditStreamSettings().catch(() => null),
      ])
      setBans(b.active_bans || [])
      setClientIp(ipInfo.client_ip)
      setSessions(activeSessions)
      if (hooks) {
        setWebhookSettings(hooks)
        setWebhookUrl(hooks.url)
      }
      if (audit) {
        setAuditStream(audit)
        setAuditHttpUrl(audit.http_url)
        setAuditSyslogHost(audit.syslog_host)
      }
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
        whitelist_firewall: settings?.whitelist_firewall,
        block_scanners: settings?.block_scanners,
        scanner_max_attempts: settings?.scanner_max_attempts,
        scanner_ban_seconds: settings?.scanner_ban_seconds,
        scanner_window_seconds: settings?.scanner_window_seconds,
        block_ip_blocked_dwell: settings?.block_ip_blocked_dwell,
        ip_blocked_dwell_seconds: settings?.ip_blocked_dwell_seconds,
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

  const handleClearBans = async () => {
    setClearingBans(true)
    try {
      const result = await clearScannerBans()
      success(result.message || 'Все баны сканеров сняты')
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка снятия банов')
    } finally {
      setClearingBans(false)
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
          <CardDescription>IP whitelist и блокировка сканеров (iptables/ipset)</CardDescription>
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

            <div className="space-y-2 rounded-md border p-4">
              <label className="flex cursor-pointer items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.whitelist_firewall}
                  disabled={
                    !ipRestrictionActive ||
                    !settings.whitelist_firewall_applicable ||
                    !settings.firewall_tools_ready
                  }
                  onChange={(e) => setSettings({ ...settings, whitelist_firewall: e.target.checked })}
                  className="mt-0.5 h-4 w-4 rounded border"
                />
                <span>
                  <span className="font-medium">Блок на порту панели (iptables)</span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    Доступ к BACKEND_PORT только с IP из whitelist (режим direct HTTP, не за Nginx).
                    {settings.whitelist_firewall_active && ' Активно.'}
                    {!settings.whitelist_firewall_applicable &&
                      ' Недоступно: панель за Nginx или на localhost.'}
                    {!settings.firewall_tools_ready &&
                      settings.whitelist_firewall_applicable &&
                      ` iptables/ipset: ${settings.firewall_tools_detail}`}
                  </span>
                </span>
              </label>
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
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.block_ip_blocked_dwell}
                disabled={!settings.ip_restriction_enabled}
                onChange={(e) =>
                  setSettings({ ...settings, block_ip_blocked_dwell: e.target.checked })
                }
                className="h-4 w-4 rounded border"
              />
              Бан за пребывание на странице «Доступ ограничен»
            </label>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Макс. попыток</Label>
                <Input
                  type="number"
                  min={1}
                  max={20}
                  value={settings.scanner_max_attempts}
                  onChange={(e) => setSettings({ ...settings, scanner_max_attempts: Number(e.target.value) })}
                />
              </div>
              <div className="space-y-2">
                <Label>Бан (сек)</Label>
                <Input
                  type="number"
                  min={60}
                  max={86400}
                  value={settings.scanner_ban_seconds}
                  onChange={(e) => setSettings({ ...settings, scanner_ban_seconds: Number(e.target.value) })}
                />
              </div>
              <div className="space-y-2">
                <Label>Окно попыток (сек)</Label>
                <Input
                  type="number"
                  min={10}
                  max={3600}
                  value={settings.scanner_window_seconds}
                  onChange={(e) =>
                    setSettings({ ...settings, scanner_window_seconds: Number(e.target.value) })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>Лимит на странице блокировки (сек)</Label>
                <Input
                  type="number"
                  min={30}
                  max={3600}
                  disabled={!settings.block_ip_blocked_dwell}
                  value={settings.ip_blocked_dwell_seconds}
                  onChange={(e) =>
                    setSettings({ ...settings, ip_blocked_dwell_seconds: Number(e.target.value) })
                  }
                />
              </div>
            </div>
          </div>

          <Button onClick={save} disabled={saving}>
            {saving ? 'Сохранение...' : 'Сохранить настройки'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Ban size={18} />
                Активные баны сканеров
              </CardTitle>
              <CardDescription>IP-адреса, временно заблокированные системой защиты</CardDescription>
            </div>
            {bans.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                disabled={clearingBans}
                onClick={() => void handleClearBans()}
              >
                {clearingBans ? 'Снятие...' : 'Снять все баны'}
              </Button>
            )}
          </div>
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

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock size={18} />
            Активные web-сессии
          </CardTitle>
          <CardDescription>
            Вкладки панели с heartbeat. Revoke принудительно разлогинивает сессию при следующем heartbeat.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {sessions.length === 0 ? (
            <EmptyState
              icon={Shield}
              title="Нет активных сессий"
              description="Сессии появятся после входа в панель"
              className="py-6"
            />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Пользователь</TableHead>
                    <TableHead>IP</TableHead>
                    <TableHead>User-Agent</TableHead>
                    <TableHead>Last seen</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sessions.map((s) => (
                    <TableRow key={s.session_id}>
                      <TableCell>
                        {s.username}
                        {s.is_current ? (
                          <Badge variant="secondary" className="ml-2">
                            текущая
                          </Badge>
                        ) : null}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{s.remote_addr || '—'}</TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs" title={s.user_agent || ''}>
                        {s.user_agent || '—'}
                      </TableCell>
                      <TableCell className="text-xs">{new Date(s.last_seen_at).toLocaleString('ru-RU')}</TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={revokingSession === s.session_id}
                          onClick={async () => {
                            setRevokingSession(s.session_id)
                            try {
                              await revokeActiveWebSession(s.session_id)
                              success('Сессия отозвана')
                              await load()
                            } catch (err) {
                              notifyError(err instanceof ApiError ? err.message : 'Ошибка revoke')
                            } finally {
                              setRevokingSession(null)
                            }
                          }}
                        >
                          Revoke
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

      <Card>
        <CardHeader>
          <CardTitle>Event webhooks</CardTitle>
          <CardDescription>
            HTTP POST на внешний URL при событиях журнала действий (HMAC-подпись в X-Webhook-Signature)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="webhook-enabled">Включить webhooks</Label>
            <Switch
              id="webhook-enabled"
              checked={webhookSettings?.enabled ?? false}
              onCheckedChange={(checked) =>
                setWebhookSettings((prev) => (prev ? { ...prev, enabled: checked } : prev))
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="webhook-url">URL</Label>
            <Input
              id="webhook-url"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://example.com/hooks/adminpanel"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="webhook-secret">Секрет (HMAC)</Label>
            <Input
              id="webhook-secret"
              type="password"
              value={webhookSecret}
              onChange={(e) => setWebhookSecret(e.target.value)}
              placeholder={webhookSettings?.secret_configured ? '••••••••' : 'не задан'}
            />
          </div>
          {webhookSettings?.events?.length ? (
            <div className="space-y-2">
              <Label>События</Label>
              <div className="grid gap-2 sm:grid-cols-2">
                {webhookSettings.events.map((event) => (
                  <label key={event.key} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={event.enabled}
                      onChange={(e) =>
                        setWebhookSettings((prev) =>
                          prev
                            ? {
                                ...prev,
                                events: prev.events.map((item) =>
                                  item.key === event.key ? { ...item, enabled: e.target.checked } : item,
                                ),
                              }
                            : prev,
                        )
                      }
                      className="h-4 w-4 rounded border"
                    />
                    <span>{event.label}</span>
                  </label>
                ))}
              </div>
            </div>
          ) : null}
          <Button
            disabled={savingWebhooks}
            onClick={async () => {
              setSavingWebhooks(true)
              try {
                const updated = await updateEventWebhookSettings({
                  url: webhookUrl,
                  secret: webhookSecret || undefined,
                  enabled: webhookSettings?.enabled,
                  events: webhookSettings?.events.map((e) => ({ key: e.key, enabled: e.enabled })),
                })
                setWebhookSettings(updated)
                setWebhookUrl(updated.url)
                setWebhookSecret('')
                success('Настройки webhooks сохранены')
              } catch (err) {
                notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения webhooks')
              } finally {
                setSavingWebhooks(false)
              }
            }}
          >
            {savingWebhooks ? 'Сохранение…' : 'Сохранить webhooks'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Audit SIEM stream</CardTitle>
          <CardDescription>
            Полный поток UserActionLog в HTTP-коллектор (ELK) и/или syslog (Wazuh). Асинхронная доставка с буфером.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="audit-stream-enabled">Включить поток</Label>
            <Switch
              id="audit-stream-enabled"
              checked={auditStream?.enabled ?? false}
              onCheckedChange={(checked) =>
                setAuditStream((prev) => (prev ? { ...prev, enabled: checked } : prev))
              }
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="audit-mode">Режим</Label>
            <select
              id="audit-mode"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={auditStream?.mode ?? 'http'}
              onChange={(e) =>
                setAuditStream((prev) =>
                  prev ? { ...prev, mode: e.target.value as AuditStreamSettings['mode'] } : prev,
                )
              }
            >
              <option value="http">HTTP</option>
              <option value="syslog">Syslog</option>
              <option value="both">HTTP + Syslog</option>
            </select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="audit-format">Формат</Label>
            <select
              id="audit-format"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={auditStream?.format ?? 'json'}
              onChange={(e) =>
                setAuditStream((prev) =>
                  prev ? { ...prev, format: e.target.value as AuditStreamSettings['format'] } : prev,
                )
              }
            >
              <option value="json">JSON (ECS-friendly)</option>
              <option value="cef">CEF</option>
            </select>
          </div>
          {(auditStream?.mode === 'http' || auditStream?.mode === 'both') && (
            <>
              <div className="grid gap-2">
                <Label htmlFor="audit-http-url">HTTP URL</Label>
                <Input
                  id="audit-http-url"
                  value={auditHttpUrl}
                  onChange={(e) => setAuditHttpUrl(e.target.value)}
                  placeholder="https://siem.example.com/ingest"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="audit-http-secret">HMAC secret (необязательно)</Label>
                <Input
                  id="audit-http-secret"
                  type="password"
                  value={auditSecret}
                  onChange={(e) => setAuditSecret(e.target.value)}
                  placeholder={auditStream?.secret_configured ? '••••••••' : ''}
                />
              </div>
            </>
          )}
          {(auditStream?.mode === 'syslog' || auditStream?.mode === 'both') && (
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="audit-syslog-host">Syslog host</Label>
                <Input
                  id="audit-syslog-host"
                  value={auditSyslogHost}
                  onChange={(e) => setAuditSyslogHost(e.target.value)}
                  placeholder="127.0.0.1"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="audit-syslog-port">Port</Label>
                <Input
                  id="audit-syslog-port"
                  type="number"
                  value={auditStream?.syslog_port ?? 514}
                  onChange={(e) =>
                    setAuditStream((prev) =>
                      prev ? { ...prev, syslog_port: Number(e.target.value) || 514 } : prev,
                    )
                  }
                />
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={savingAuditStream}
              onClick={async () => {
                setSavingAuditStream(true)
                try {
                  const updated = await updateAuditStreamSettings({
                    enabled: auditStream?.enabled,
                    mode: auditStream?.mode,
                    format: auditStream?.format,
                    http_url: auditHttpUrl,
                    secret: auditSecret || undefined,
                    syslog_host: auditSyslogHost,
                    syslog_port: auditStream?.syslog_port,
                    syslog_protocol: auditStream?.syslog_protocol,
                  })
                  setAuditStream(updated)
                  setAuditHttpUrl(updated.http_url)
                  setAuditSyslogHost(updated.syslog_host)
                  setAuditSecret('')
                  success('Настройки audit stream сохранены')
                } catch (err) {
                  notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения audit stream')
                } finally {
                  setSavingAuditStream(false)
                }
              }}
            >
              {savingAuditStream ? 'Сохранение…' : 'Сохранить audit stream'}
            </Button>
            <Button
              variant="outline"
              disabled={testingAuditStream || !auditStream?.enabled}
              onClick={async () => {
                setTestingAuditStream(true)
                try {
                  const res = await testAuditStream()
                  success(JSON.stringify(res.results))
                } catch (err) {
                  notifyError(err instanceof ApiError ? err.message : 'Тест audit stream не удался')
                } finally {
                  setTestingAuditStream(false)
                }
              }}
            >
              {testingAuditStream ? 'Тест…' : 'Тестовое событие'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
