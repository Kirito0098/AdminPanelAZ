import { useEffect, useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Ban,
  Clock,
  Globe,
  LogOut,
  Monitor,
  Network,
  Plus,
  Radar,
  Save,
  Shield,
  ShieldAlert,
  ShieldOff,
  Unlock,
  Webhook,
  X,
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

function SectionHeading({
  title,
  description,
}: {
  title: string
  description: string
}) {
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
          tone === 'warning' && 'bg-destructive/15 text-destructive',
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

function ListRow({
  children,
  action,
}: {
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <li className="flex items-center justify-between gap-3 rounded-xl border bg-card/50 px-3 py-2.5 transition-colors hover:bg-muted/30">
      <div className="min-w-0 flex-1">{children}</div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </li>
  )
}

function PanelEmpty({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon
  title: string
  description: string
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-muted-foreground/20 bg-muted/10 px-4 py-8 text-center">
      <Icon className="mb-2 h-8 w-8 text-muted-foreground/70" />
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 max-w-xs text-xs text-muted-foreground">{description}</p>
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
        <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 md:col-span-2">
          <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-2xl" />
          <div className="relative grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricPill
              icon={Network}
              label="Ограничение по IP"
              value={ipRestrictionActive ? 'Включено' : 'Выключено'}
              tone={ipRestrictionActive ? 'success' : 'muted'}
            />
            <MetricPill
              icon={Radar}
              label="Блокировка сканеров"
              value={settings.block_scanners ? 'Активна' : 'Выключена'}
              tone={settings.block_scanners ? 'success' : 'muted'}
            />
            <MetricPill
              icon={Ban}
              label="Заблокировано"
              value={bans.length === 0 ? 'Никого' : `${bans.length} адр.`}
              tone={bans.length > 0 ? 'warning' : 'muted'}
            />
            <MetricPill
              icon={Globe}
              label="Ваш IP"
              value={clientIp ?? 'не определён'}
              tone={clientIp ? 'default' : 'muted'}
            />
          </div>
        </div>

        {ipListEmpty && (
          <SettingsAlert variant="warning" title="Список разрешённых адресов пуст" className="md:col-span-2">
            При включённом ограничении без адресов в списке вход в панель будет недоступен. Добавьте свой IP или
            временный доступ ниже.
          </SettingsAlert>
        )}

        <SectionHeading
          title="Доступ к панели"
          description="Кто может открыть панель и как выдать временный доступ"
        />

        <div className="grid gap-4 md:col-span-2 md:grid-cols-2 md:items-stretch">
        <Card className="flex h-full flex-col overflow-hidden shadow-sm">
          <div className="h-1 bg-gradient-to-r from-primary/80 to-primary/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Network size={18} />
              Кто может открыть панель
            </CardTitle>
            <CardDescription>
              Разрешите вход только с доверенных адресов — особенно если панель доступна из интернета
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col space-y-4">
            <ToggleRow
              id="ip-restriction"
              label="Разрешать вход только с указанных IP-адресов"
              description="Все остальные подключения увидят страницу «Доступ запрещён»"
              checked={settings.ip_restriction_enabled}
              onCheckedChange={(checked) => saveWithSettingsPatch({ ip_restriction_enabled: checked })}
            />

            {ipRestrictionActive && (
              <>
                <div className="space-y-2 rounded-xl border bg-muted/20 p-4">
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

        <Card className="flex h-full flex-col overflow-hidden shadow-sm">
          <div className="h-1 bg-gradient-to-r from-amber-500/70 to-amber-500/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock size={18} />
              Временный доступ по IP
            </CardTitle>
            <CardDescription>
              Разрешить вход с адреса на ограниченное время — без добавления в постоянный список
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col space-y-4">
            {!ipRestrictionActive ? (
              <div className="flex flex-1 items-start">
                <SettingsAlert variant="info" className="w-full">
                  Включите ограничение по IP слева — тогда здесь можно выдать временный доступ.
                </SettingsAlert>
              </div>
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
                          'rounded-lg border px-4 py-2 text-sm font-medium transition-all',
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

                <div className="flex flex-col gap-2 sm:flex-row">
                  <Button
                    type="button"
                    className="flex-1"
                    disabled={!clientIp}
                    onClick={() => handleAddTempWhitelist(clientIp ?? undefined)}
                  >
                    <Plus size={16} />
                    {addingTemp ? 'Добавление...' : 'Текущий IP'}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1"
                    disabled={!tempIpInput.trim()}
                    onClick={() => handleAddTempWhitelist()}
                  >
                    Указанный IP
                  </Button>
                </div>
              </fieldset>
            )}

            {settings.temp_whitelist.length > 0 && (
              <ul className="space-y-2 border-t pt-4">
                <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Активные пропуска
                </p>
                {settings.temp_whitelist.map((entry) => (
                  <ListRow
                    key={entry.ip}
                    action={
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                        disabled={!ipRestrictionActive || removingTempIp === entry.ip}
                        onClick={() => handleRemoveTempWhitelist(entry.ip)}
                        title="Удалить"
                      >
                        {removingTempIp === entry.ip ? '…' : <X size={14} />}
                      </Button>
                    }
                  >
                    <p className="truncate font-mono text-sm font-medium">{entry.ip}</p>
                    <p className="text-xs text-muted-foreground">
                      до {formatDateTime(entry.expires_at)} · {entry.hours} ч
                    </p>
                  </ListRow>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        </div>

        <SectionHeading
          title="Защита от атак"
          description="Автоблокировка сканеров и злоумышленников на странице отказа"
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-violet-500/70 to-violet-500/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldAlert size={18} />
              Защита от перебора и сканирования
            </CardTitle>
            <CardDescription>
              Автоматически блокируйте подозрительные подключения и злоумышленников, застрявших на странице отказа
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
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
                  label="Блокировать «зависших» на странице отказа"
                  description="Полезно против ботов, которые долго остаются на закрытой панели"
                  checked={settings.block_ip_blocked_dwell}
                  onCheckedChange={(checked) => saveWithSettingsPatch({ block_ip_blocked_dwell: checked })}
                />
              )}
            </div>

            {settings.block_scanners && (
              <div className="grid gap-3 rounded-xl border bg-muted/20 p-4 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor="scanner-max" className="text-xs">
                    Неудачных попыток
                  </Label>
                  <Input
                    id="scanner-max"
                    type="number"
                    min={1}
                    max={20}
                    value={settings.scanner_max_attempts}
                    onChange={(e) => setSettings({ ...settings, scanner_max_attempts: Number(e.target.value) })}
                  />
                  <p className="text-[11px] text-muted-foreground">До блокировки</p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="scanner-ban" className="text-xs">
                    Блокировка, сек
                  </Label>
                  <Input
                    id="scanner-ban"
                    type="number"
                    min={60}
                    max={86400}
                    value={settings.scanner_ban_seconds}
                    onChange={(e) => setSettings({ ...settings, scanner_ban_seconds: Number(e.target.value) })}
                  />
                  <p className="text-[11px] text-muted-foreground">
                    {formatRemainingSeconds(settings.scanner_ban_seconds)}
                  </p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="scanner-window" className="text-xs">
                    Окно, сек
                  </Label>
                  <Input
                    id="scanner-window"
                    type="number"
                    min={10}
                    max={3600}
                    value={settings.scanner_window_seconds}
                    onChange={(e) => setSettings({ ...settings, scanner_window_seconds: Number(e.target.value) })}
                  />
                  <p className="text-[11px] text-muted-foreground">Период подсчёта</p>
                </div>
              </div>
            )}

            {settings.block_ip_blocked_dwell && settings.ip_restriction_enabled && (
              <div className="max-w-sm space-y-1.5 rounded-xl border bg-muted/20 p-4">
                <Label htmlFor="dwell-seconds" className="text-xs">
                  Макс. время на странице блокировки, сек
                </Label>
                <Input
                  id="dwell-seconds"
                  type="number"
                  min={30}
                  max={3600}
                  value={settings.ip_blocked_dwell_seconds}
                  onChange={(e) => setSettings({ ...settings, ip_blocked_dwell_seconds: Number(e.target.value) })}
                />
                <p className="text-[11px] text-muted-foreground">Сколько можно «висеть» на странице отказа</p>
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

        <SectionHeading
          title="Активность"
          description="Открытые сессии и адреса, которые сейчас заблокированы"
        />

        <div className="grid gap-4 md:col-span-2 md:grid-cols-2 md:items-stretch">
        <Card className="flex h-full flex-col overflow-hidden shadow-sm">
          <div className="h-1 bg-gradient-to-r from-sky-500/70 to-sky-500/15" />
          <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Monitor size={18} />
                Активные web-сессии
              </CardTitle>
              <CardDescription className="mt-1.5">
                Открытые вкладки. «Отозвать» разлогинивает при следующем heartbeat.
              </CardDescription>
            </div>
            {sessions.length > 0 && (
              <Badge variant="secondary" className="shrink-0">
                {sessions.length}
              </Badge>
            )}
          </CardHeader>
          <CardContent className="flex flex-1 flex-col">
            {sessions.length === 0 ? (
              <PanelEmpty
                icon={Shield}
                title="Нет активных сессий"
                description="Сессии появятся после входа в панель"
              />
            ) : (
              <ul className="space-y-2">
                {sessions.map((s) => (
                  <ListRow
                    key={s.session_id}
                    action={
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
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
                        <LogOut size={14} />
                        {revokingSession === s.session_id ? '…' : 'Отозвать'}
                      </Button>
                    }
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">{s.username}</span>
                      {s.is_current ? <Badge variant="default">вы</Badge> : null}
                    </div>
                    <p className="mt-0.5 font-mono text-xs text-muted-foreground">{s.remote_addr || '—'}</p>
                    <p className="truncate text-xs text-muted-foreground" title={s.user_agent || ''}>
                      {s.user_agent || '—'}
                    </p>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {LABEL_LAST_SEEN}: {formatDateTime(s.last_seen_at)}
                    </p>
                  </ListRow>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className="flex h-full flex-col overflow-hidden shadow-sm">
          <div
            className={cn(
              'h-1 bg-gradient-to-r',
              bans.length > 0 ? 'from-destructive/80 to-destructive/15' : 'from-muted-foreground/30 to-muted/10',
            )}
          />
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Ban size={18} />
                Активные блокировки
              </CardTitle>
              <CardDescription className="mt-1.5">
                Адреса, которые сейчас не могут подключиться к панели
              </CardDescription>
            </div>
            {bans.length > 0 && (
              <Button size="sm" variant="outline" disabled={clearingBans} onClick={() => void handleClearBans()}>
                {clearingBans ? 'Снятие...' : 'Снять все'}
              </Button>
            )}
          </CardHeader>
          <CardContent className="flex flex-1 flex-col">
            {bans.length === 0 ? (
              <PanelEmpty
                icon={ShieldOff}
                title="Активных банов нет"
                description="Заблокированные сканеры появятся здесь автоматически"
              />
            ) : (
              <ul className="space-y-2">
                {bans.map((b) => (
                  <ListRow
                    key={b.ip}
                    action={
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
                        onClick={() => handleUnban(b.ip)}
                      >
                        <Unlock size={14} />
                        Разблок.
                      </Button>
                    }
                  >
                    <p className="truncate font-mono text-sm font-medium">{b.ip}</p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                      <span className="text-xs text-muted-foreground">
                        {formatRemainingSeconds(b.remaining_seconds)}
                      </span>
                      <Badge variant={b.long_term ? 'destructive' : 'secondary'} className="text-[10px]">
                        {b.strikes} попыток{b.long_term ? ' · долгий' : ''}
                      </Badge>
                    </div>
                  </ListRow>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        </div>

        <SectionHeading
          title="Интеграции"
          description="Уведомления и пересылка журнала во внешние системы"
        />

        <div className="grid gap-4 md:col-span-2 md:grid-cols-2 md:items-stretch">
        <Card className="flex h-full flex-col overflow-hidden shadow-sm">
          <div className="h-1 bg-gradient-to-r from-emerald-500/70 to-emerald-500/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Webhook size={18} />
              Уведомления
            </CardTitle>
            <CardDescription>События из журнала действий на внешний URL</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col space-y-4">
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
              <div className="space-y-4 rounded-xl border bg-muted/20 p-4">
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
                  <div className="space-y-2">
                    <Label className="text-xs">События</Label>
                    <div className="grid gap-1 sm:grid-cols-2">
                      {webhookSettings.events.map((event) => (
                        <label
                          key={event.key}
                          className="flex cursor-pointer items-center gap-2 rounded-lg border bg-card/50 px-2.5 py-2 text-sm transition-colors hover:bg-muted/50"
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
              </div>
            )}
            <Button
              className="mt-auto w-full"
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
              <Save size={16} />
              {savingWebhooks ? 'Сохранение…' : 'Сохранить'}
            </Button>
          </CardContent>
        </Card>

        <Card className="flex h-full flex-col overflow-hidden shadow-sm">
          <div className="h-1 bg-gradient-to-r from-cyan-500/70 to-cyan-500/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield size={18} />
              Журнал во внешнюю систему
            </CardTitle>
            <CardDescription>SIEM, syslog или HTTP для продвинутых сценариев</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col space-y-4">
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
              <div className="space-y-4 rounded-xl border bg-muted/20 p-4">
                <div className="grid gap-3 sm:grid-cols-2">
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
                </div>
                {(auditStream.mode === 'http' || auditStream.mode === 'both') && (
                  <div className="space-y-3 rounded-lg border bg-card/50 p-3">
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
                  <div className="grid gap-3 rounded-lg border bg-card/50 p-3 sm:grid-cols-2">
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
              </div>
            )}
            <Button
              className="mt-auto w-full"
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
              <Save size={16} />
              {savingAuditStream ? 'Сохранение…' : 'Сохранить'}
            </Button>
          </CardContent>
        </Card>
        </div>

        <div className="md:col-span-2">
          <SecretsRotationWizard />
        </div>
      </div>
    </div>
  )
}
