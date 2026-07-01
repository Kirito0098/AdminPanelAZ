import { useEffect, useState } from 'react'
import {
  Ban,
  Clock,
  Globe,
  Monitor,
  Network,
  Radar,
  Save,
  Shield,
  ShieldAlert,
  ShieldOff,
  Webhook,
} from 'lucide-react'
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
import SettingsAlert from '@/components/settings/SettingsAlert'
import SecretsRotationWizard from '@/components/settings/SecretsRotationWizard'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useNotifications } from '@/context/NotificationContext'
import { formatDateTime } from '@/lib/datetime'
import { LABEL_LAST_SEEN } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import type { ActiveWebSession, AuditStreamSettings, EventWebhookSettings, ScannerBan, SecuritySettings } from '@/types'

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
        'flex items-start justify-between gap-4 rounded-lg border p-4 transition-colors',
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

function StatusTile({
  icon: Icon,
  label,
  value,
  active,
}: {
  icon: typeof Shield
  label: string
  value: string
  active?: boolean
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card p-3">
      <div
        className={cn(
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-md',
          active ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground',
        )}
      >
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-medium">{value}</p>
      </div>
    </div>
  )
}

function formatRemainingSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds} сек`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} мин`
  const hours = Math.floor(minutes / 60)
  const remMin = minutes % 60
  return remMin > 0 ? `${hours} ч ${remMin} мин` : `${hours} ч`
}

const TEMP_HOURS = [1, 12, 24] as const

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

  const persistSettings = async (snapshot: { settings: SecuritySettings; allowedIps: string }) => {
    setSaving(true)
    try {
      const updated = await updateSecuritySettings({
        ip_restriction_enabled: snapshot.settings.ip_restriction_enabled,
        allowed_ips: snapshot.allowedIps.split(',').map((s) => s.trim()).filter(Boolean),
        whitelist_firewall: snapshot.settings.whitelist_firewall,
        block_scanners: snapshot.settings.block_scanners,
        scanner_max_attempts: snapshot.settings.scanner_max_attempts,
        scanner_ban_seconds: snapshot.settings.scanner_ban_seconds,
        scanner_window_seconds: snapshot.settings.scanner_window_seconds,
        block_ip_blocked_dwell: snapshot.settings.block_ip_blocked_dwell,
        ip_blocked_dwell_seconds: snapshot.settings.ip_blocked_dwell_seconds,
      })
      setSettings(updated)
      setAllowedIps(updated.allowed_ips.join(', '))
      success('Настройки безопасности сохранены')
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const save = () => {
    if (!settings) return
    void persistSettings({ settings, allowedIps })
  }

  const saveWithSettingsPatch = (patch: Partial<SecuritySettings>) => {
    if (!settings) return
    const next = { ...settings, ...patch }
    setSettings(next)
    void persistSettings({ settings: next, allowedIps })
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
  const allowedIpsList = allowedIps.split(',').map((s) => s.trim()).filter(Boolean)
  const ipListEmpty = ipRestrictionActive && allowedIpsList.length === 0
  const scannerDetailsVisible =
    settings?.block_scanners ||
    Boolean(settings?.ip_restriction_enabled && settings?.block_ip_blocked_dwell)

  if (loading) {
    return <Spinner label="Загрузка настроек безопасности..." className="py-12" />
  }

  if (!settings) return null

  return (
    <div className="space-y-4">
      <InlineProgressBar active={saving} label="Сохранение настроек..." />

      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        <div className="grid grid-cols-2 gap-3 md:col-span-2">
          <StatusTile
            icon={Network}
            label="Ограничение по IP"
            value={ipRestrictionActive ? 'Включено' : 'Выключено'}
            active={ipRestrictionActive}
          />
          <StatusTile
            icon={Radar}
            label="Блокировка сканеров"
            value={settings.block_scanners ? 'Активна' : 'Выключена'}
            active={settings.block_scanners}
          />
          <StatusTile
            icon={Ban}
            label="Заблокировано сейчас"
            value={bans.length === 0 ? 'Никого' : `${bans.length} адр.`}
            active={bans.length > 0}
          />
          <StatusTile
            icon={Globe}
            label="Ваш IP"
            value={clientIp ?? 'не определён'}
            active={Boolean(clientIp)}
          />
        </div>

        {ipListEmpty && (
          <SettingsAlert variant="warning" title="Список разрешённых адресов пуст" className="md:col-span-2">
            При включённом ограничении без адресов в списке вход в панель будет недоступен. Добавьте свой IP или
            временный доступ ниже.
          </SettingsAlert>
        )}

      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Network size={18} />
            Кто может открыть панель
          </CardTitle>
          <CardDescription>
            Разрешите вход только с доверенных адресов — особенно если панель доступна из интернета
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ToggleRow
            id="ip-restriction"
            label="Разрешать вход только с указанных IP-адресов"
            description="Все остальные подключения увидят страницу «Доступ запрещён»"
            checked={settings.ip_restriction_enabled}
            onCheckedChange={(checked) => saveWithSettingsPatch({ ip_restriction_enabled: checked })}
          />

          {ipRestrictionActive && (
            <>
              <div className="space-y-2 rounded-lg border p-4">
                <Label htmlFor="allowed-ips">Разрешённые адреса</Label>
                <Input
                  id="allowed-ips"
                  value={allowedIps}
                  onChange={(e) => setAllowedIps(e.target.value)}
                  placeholder="192.168.1.0/24, 10.0.0.1"
                  className="font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground">
                  Несколько адресов через запятую. Подсеть:{' '}
                  <code className="text-foreground">192.168.1.0/24</code> — вся домашняя сеть.
                </p>
              </div>

              <ToggleRow
                id="whitelist-firewall"
                label="Дополнительная блокировка на уровне сервера"
                description={[
                  'Закрывает доступ к панели для всех, кроме адресов из списка (только при прямом подключении без Nginx).',
                  settings.whitelist_firewall_active && 'Сейчас включено.',
                  !settings.whitelist_firewall_applicable &&
                    'Недоступно: панель работает через Nginx или только на localhost.',
                  !settings.firewall_tools_ready &&
                    settings.whitelist_firewall_applicable &&
                    `Требуются системные средства: ${settings.firewall_tools_detail}`,
                ]
                  .filter(Boolean)
                  .join(' ')}
                checked={settings.whitelist_firewall}
                disabled={!settings.whitelist_firewall_applicable || !settings.firewall_tools_ready}
                onCheckedChange={(checked) => saveWithSettingsPatch({ whitelist_firewall: checked })}
              />

              <div className="flex justify-end border-t pt-4">
                <Button onClick={save} disabled={saving}>
                  <Save size={16} />
                  {saving ? 'Сохранение...' : 'Сохранить'}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock size={18} />
            Временный доступ по IP
          </CardTitle>
          <CardDescription>
            Разрешить вход с адреса на ограниченное время — без добавления в постоянный список
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!ipRestrictionActive ? (
            <SettingsAlert variant="info">
              Включите ограничение по IP слева — тогда здесь можно выдать временный доступ.
            </SettingsAlert>
          ) : (
            <fieldset disabled={addingTemp} className="space-y-4">
              <div className="space-y-2">
                <Label>Срок доступа</Label>
                <div className="flex flex-wrap gap-2">
                  {TEMP_HOURS.map((h) => (
                    <button
                      key={h}
                      type="button"
                      onClick={() => setTempHours(h)}
                      className={cn(
                        'rounded-lg border px-4 py-2 text-sm font-medium transition-colors',
                        tempHours === h
                          ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
                          : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                      )}
                    >
                      {h} ч.
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="temp-ip">IP-адрес (необязательно)</Label>
                <Input
                  id="temp-ip"
                  value={tempIpInput}
                  onChange={(e) => setTempIpInput(e.target.value)}
                  placeholder={clientIp ? `Пусто = ${clientIp}` : '192.168.1.100'}
                  className="font-mono"
                />
              </div>

              <div className="flex flex-col gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={!clientIp}
                  onClick={() => handleAddTempWhitelist(clientIp ?? undefined)}
                >
                  {addingTemp ? 'Добавление...' : 'Текущий IP'}
                </Button>
                <Button type="button" disabled={!tempIpInput.trim()} onClick={() => handleAddTempWhitelist()}>
                  Указанный IP
                </Button>
              </div>
            </fieldset>
          )}

          {settings.temp_whitelist.length > 0 && (
            <ul className="space-y-2">
              {settings.temp_whitelist.map((entry) => (
                <li
                  key={entry.ip}
                  className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm font-medium">{entry.ip}</p>
                    <p className="text-xs text-muted-foreground">
                      до {formatDateTime(entry.expires_at)} · {entry.hours} ч
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="shrink-0"
                    disabled={!ipRestrictionActive || removingTempIp === entry.ip}
                    onClick={() => handleRemoveTempWhitelist(entry.ip)}
                  >
                    {removingTempIp === entry.ip ? '...' : 'Удалить'}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldAlert size={18} />
            Защита от перебора и сканирования
          </CardTitle>
          <CardDescription>
            Автоматически блокируйте подозрительные подключения и злоумышленников, застрявших на странице отказа
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ToggleRow
            id="block-scanners"
            label="Автоматически блокировать подозрительные подключения"
            description="Сканеры портов и множественные неудачные попытки входа"
            checked={settings.block_scanners}
            onCheckedChange={(checked) => saveWithSettingsPatch({ block_scanners: checked })}
          />

          {settings.ip_restriction_enabled && (
            <ToggleRow
              id="block-dwell"
              label="Блокировать тех, кто долго остаётся на странице «Доступ запрещён»"
              description="Полезно против ботов, которые «висят» на закрытой панели"
              checked={settings.block_ip_blocked_dwell}
              onCheckedChange={(checked) => saveWithSettingsPatch({ block_ip_blocked_dwell: checked })}
            />
          )}

          {settings.block_scanners && (
            <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
              <div className="space-y-2">
                <Label htmlFor="scanner-max">Неудачных попыток</Label>
                <Input
                  id="scanner-max"
                  type="number"
                  min={1}
                  max={20}
                  value={settings.scanner_max_attempts}
                  onChange={(e) => setSettings({ ...settings, scanner_max_attempts: Number(e.target.value) })}
                />
                <p className="text-xs text-muted-foreground">После этого адрес блокируется</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="scanner-ban">Длительность блокировки, сек</Label>
                <Input
                  id="scanner-ban"
                  type="number"
                  min={60}
                  max={86400}
                  value={settings.scanner_ban_seconds}
                  onChange={(e) => setSettings({ ...settings, scanner_ban_seconds: Number(e.target.value) })}
                />
                <p className="text-xs text-muted-foreground">{formatRemainingSeconds(settings.scanner_ban_seconds)}</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="scanner-window">Окно подсчёта, сек</Label>
                <Input
                  id="scanner-window"
                  type="number"
                  min={10}
                  max={3600}
                  value={settings.scanner_window_seconds}
                  onChange={(e) => setSettings({ ...settings, scanner_window_seconds: Number(e.target.value) })}
                />
                <p className="text-xs text-muted-foreground">За какой период считаются попытки</p>
              </div>
            </div>
          )}

          {settings.block_ip_blocked_dwell && settings.ip_restriction_enabled && (
            <div className="space-y-2 rounded-lg border bg-muted/20 p-4">
              <Label htmlFor="dwell-seconds">Макс. время на странице блокировки, сек</Label>
              <Input
                id="dwell-seconds"
                type="number"
                min={30}
                max={3600}
                value={settings.ip_blocked_dwell_seconds}
                onChange={(e) => setSettings({ ...settings, ip_blocked_dwell_seconds: Number(e.target.value) })}
              />
              <p className="text-xs text-muted-foreground">Сколько можно «висеть» на странице отказа</p>
            </div>
          )}

          {scannerDetailsVisible && (
            <div className="flex justify-end border-t pt-4">
              <Button onClick={save} disabled={saving}>
                <Save size={16} />
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Monitor size={18} />
            Активные web-сессии
          </CardTitle>
          <CardDescription>
            Открытые вкладки. «Отозвать» разлогинивает при следующем heartbeat.
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
            <ul className="space-y-2">
              {sessions.map((s) => (
                <li key={s.session_id} className="rounded-lg border px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-medium">{s.username}</span>
                        {s.is_current ? <Badge variant="default">вы</Badge> : null}
                      </div>
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">{s.remote_addr || '—'}</p>
                      <p className="truncate text-xs text-muted-foreground" title={s.user_agent || ''}>
                        {s.user_agent || '—'}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {LABEL_LAST_SEEN}: {formatDateTime(s.last_seen_at)}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="shrink-0"
                      disabled={revokingSession === s.session_id}
                      onClick={async () => {
                        setRevokingSession(s.session_id)
                        try {
                          await revokeActiveWebSession(s.session_id)
                          success('Сессия отозвана')
                          await load()
                        } catch (err) {
                          notifyError(err instanceof ApiError ? err.message : 'Ошибка отзыва сессии')
                        } finally {
                          setRevokingSession(null)
                        }
                      }}
                    >
                      {revokingSession === s.session_id ? '...' : 'Отозвать'}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="h-full">
        <CardHeader>
          <div className="flex flex-col gap-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Ban size={18} />
                Активные блокировки
              </CardTitle>
              <CardDescription>Адреса, которые сейчас не могут подключиться к панели</CardDescription>
            </div>
            {bans.length > 0 && (
              <Button size="sm" variant="outline" disabled={clearingBans} onClick={() => void handleClearBans()}>
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
            <ul className="space-y-2">
              {bans.map((b) => (
                <li
                  key={b.ip}
                  className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm font-medium">{b.ip}</p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <span className="text-xs text-muted-foreground">
                        {formatRemainingSeconds(b.remaining_seconds)}
                      </span>
                      <Badge variant={b.long_term ? 'destructive' : 'secondary'} className="text-[10px]">
                        {b.strikes} попыток{b.long_term ? ' · долгий' : ''}
                      </Badge>
                    </div>
                  </div>
                  <Button size="sm" variant="outline" className="shrink-0" onClick={() => handleUnban(b.ip)}>
                    Разблок.
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Webhook size={18} />
            Уведомления
          </CardTitle>
          <CardDescription>События из журнала действий на внешний URL</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ToggleRow
            id="webhook-enabled"
            label="Отправлять события на внешний URL"
            description="Интеграция с системами мониторинга и автоматизации"
            checked={webhookSettings?.enabled ?? false}
            onCheckedChange={(checked) =>
              setWebhookSettings((prev) => (prev ? { ...prev, enabled: checked } : prev))
            }
          />

          {webhookSettings?.enabled && (
            <>
              <div className="space-y-2">
                <Label htmlFor="webhook-url">Адрес для уведомлений</Label>
                <Input
                  id="webhook-url"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  placeholder="https://example.com/hooks/adminpanel"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="webhook-secret">Секретный ключ</Label>
                <Input
                  id="webhook-secret"
                  type="password"
                  value={webhookSecret}
                  onChange={(e) => setWebhookSecret(e.target.value)}
                  placeholder={webhookSettings?.secret_configured ? '••••••••' : 'не задан'}
                />
              </div>
              {webhookSettings.events?.length ? (
                <div className="space-y-2 rounded-lg border p-3">
                  <Label className="text-xs">События</Label>
                  <div className="space-y-1">
                    {webhookSettings.events.map((event) => (
                      <label
                        key={event.key}
                        className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1 text-sm hover:bg-muted/50"
                      >
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
                        <span className="text-xs">{event.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          )}
          <Button
            className="w-full"
            variant={webhookSettings?.enabled ? 'default' : 'outline'}
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
            {savingWebhooks ? 'Сохранение…' : 'Сохранить'}
          </Button>
        </CardContent>
      </Card>

      <Card className="h-full">
        <CardHeader>
          <CardTitle className="text-base">Журнал во внешнюю систему</CardTitle>
          <CardDescription>SIEM, syslog или HTTP для продвинутых сценариев</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ToggleRow
            id="audit-stream-enabled"
            label="Пересылать журнал действий"
            description="HTTP-эндпоинт или syslog для мониторинга безопасности"
            checked={auditStream?.enabled ?? false}
            onCheckedChange={(checked) =>
              setAuditStream((prev) => (prev ? { ...prev, enabled: checked } : prev))
            }
          />

          {auditStream?.enabled && (
            <>
              <div className="space-y-2">
                <Label htmlFor="audit-mode">Режим</Label>
                <Select
                  value={auditStream.mode ?? 'http'}
                  onValueChange={(value) =>
                    setAuditStream((prev) =>
                      prev ? { ...prev, mode: value as AuditStreamSettings['mode'] } : prev,
                    )
                  }
                >
                  <SelectTrigger id="audit-mode">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="http">HTTP</SelectItem>
                    <SelectItem value="syslog">Syslog</SelectItem>
                    <SelectItem value="both">HTTP + Syslog</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="audit-format">Формат</Label>
                <Select
                  value={auditStream.format ?? 'json'}
                  onValueChange={(value) =>
                    setAuditStream((prev) =>
                      prev ? { ...prev, format: value as AuditStreamSettings['format'] } : prev,
                    )
                  }
                >
                  <SelectTrigger id="audit-format">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="json">JSON (ECS-friendly)</SelectItem>
                    <SelectItem value="cef">CEF</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {(auditStream.mode === 'http' || auditStream.mode === 'both') && (
                <div className="space-y-3 rounded-lg border p-3">
                  <div className="space-y-2">
                    <Label htmlFor="audit-http-url">HTTP URL</Label>
                    <Input
                      id="audit-http-url"
                      value={auditHttpUrl}
                      onChange={(e) => setAuditHttpUrl(e.target.value)}
                      placeholder="https://siem.example.com/ingest"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="audit-http-secret">HMAC secret</Label>
                    <Input
                      id="audit-http-secret"
                      type="password"
                      value={auditSecret}
                      onChange={(e) => setAuditSecret(e.target.value)}
                      placeholder={auditStream.secret_configured ? '••••••••' : ''}
                    />
                  </div>
                </div>
              )}
              {(auditStream.mode === 'syslog' || auditStream.mode === 'both') && (
                <div className="space-y-3 rounded-lg border p-3">
                  <div className="space-y-2">
                    <Label htmlFor="audit-syslog-host">Хост syslog</Label>
                    <Input
                      id="audit-syslog-host"
                      value={auditSyslogHost}
                      onChange={(e) => setAuditSyslogHost(e.target.value)}
                      placeholder="127.0.0.1"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="audit-syslog-port">Порт</Label>
                    <Input
                      id="audit-syslog-port"
                      type="number"
                      value={auditStream.syslog_port ?? 514}
                      onChange={(e) =>
                        setAuditStream((prev) =>
                          prev ? { ...prev, syslog_port: Number(e.target.value) || 514 } : prev,
                        )
                      }
                    />
                  </div>
                </div>
              )}
              <Button
                variant="outline"
                className="w-full"
                disabled={testingAuditStream}
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
            </>
          )}
          <Button
            className="w-full"
            variant={auditStream?.enabled ? 'default' : 'outline'}
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
            {savingAuditStream ? 'Сохранение…' : 'Сохранить'}
          </Button>
        </CardContent>
      </Card>

      <SecretsRotationWizard />
      </div>
    </div>
  )
}
