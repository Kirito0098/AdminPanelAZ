import { useEffect, useMemo, useRef, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Archive,
  ArchiveX,
  CalendarClock,
  Check,
  Database,
  Download,
  HardDrive,
  LayoutDashboard,
  ListTree,
  RotateCcw,
  Save,
  Send,
  Server,
  Trash2,
  Upload,
} from 'lucide-react'
import {
  ApiError,
  createBackup,
  deleteBackup,
  downloadBackup,
  getBackupSettings,
  getBackups,
  restoreBackup,
  updateBackupSettings,
  uploadBackup,
} from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { formatDateTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { BackupEntry, BackupSettings } from '@/types'

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}

const COMPONENT_LABELS: Record<string, string> = {
  db: 'База AdminPanel',
  cidr_db: 'База CIDR',
  env: '.env панели',
  configs: 'Списки AntiZapret',
  database: 'База AdminPanel',
  antizapret_lists: 'Списки AntiZapret',
  antizapret_backup: 'Архив AntiZapret',
}

const ADMIN_PANEL_ALWAYS_INCLUDED = [
  'База данных — пользователи, роли, настройки, узлы и журналы',
  'База CIDR — подсети для карты маршрутизации в панели',
  'Файл .env — пароли, ключи и параметры запуска панели',
] as const

const INTERVAL_PRESETS = [1, 3, 7, 14] as const
const RETENTION_PRESETS = [3, 5, 10] as const

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="md:col-span-2">
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
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
  tone?: 'default' | 'success' | 'muted'
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card/80 p-3 shadow-sm backdrop-blur-sm">
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          tone === 'success' && 'bg-primary/15 text-primary',
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

function BackupScopeBlock({
  icon: Icon,
  title,
  subtitle,
  children,
}: {
  icon: LucideIcon
  title: string
  subtitle: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-3 rounded-xl border bg-muted/15 p-4">
      <div className="flex gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon size={18} />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{subtitle}</p>
        </div>
      </div>
      {children}
    </div>
  )
}

function IncludedItemsList({ items }: { items: readonly string[] }) {
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item} className="flex gap-2 text-xs leading-relaxed text-muted-foreground">
          <Check size={14} className="mt-0.5 shrink-0 text-primary" strokeWidth={2.5} />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function OptionCard({
  icon: Icon,
  label,
  description,
  checked,
  onChange,
}: {
  icon: LucideIcon
  label: string
  description: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={`${label}: ${checked ? 'включено' : 'выключено'}`}
      onClick={() => onChange(!checked)}
      className={cn(
        'group flex w-full cursor-pointer items-start gap-3 rounded-xl border-2 p-4 text-left transition-all',
        checked
          ? 'border-primary bg-primary/10 shadow-sm ring-2 ring-primary/25'
          : 'border-border bg-card hover:border-primary/50 hover:bg-muted/40',
      )}
    >
      <div
        className={cn(
          'flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 transition-colors',
          checked
            ? 'border-primary bg-primary text-primary-foreground'
            : 'border-muted-foreground/60 bg-background group-hover:border-primary/60',
        )}
        aria-hidden
      >
        {checked ? <Check size={14} strokeWidth={3} /> : null}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Icon size={16} className={cn('shrink-0', checked ? 'text-primary' : 'text-muted-foreground')} />
            <span className="text-sm font-medium">{label}</span>
          </div>
          <Badge variant={checked ? 'default' : 'outline'} className="shrink-0 text-[10px]">
            {checked ? 'Вкл.' : 'Выкл.'}
          </Badge>
        </div>
        <span className="mt-1.5 block text-xs leading-relaxed text-muted-foreground">{description}</span>
      </div>
    </button>
  )
}

export default function BackupTab() {
  const { success, error: notifyError } = useNotifications()
  const { withInline } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [backups, setBackups] = useState<BackupEntry[]>([])
  const [settings, setSettings] = useState<BackupSettings | null>(null)
  const [settingsDraft, setSettingsDraft] = useState<BackupSettings | null>(null)
  const [includeConfigs, setIncludeConfigs] = useState(false)
  const [includeAntizapretBackup, setIncludeAntizapretBackup] = useState(false)
  const [loading, setLoading] = useState(true)
  const [savingSettings, setSavingSettings] = useState(false)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const pendingRestoreRef = useRef(false)

  const load = async () => {
    const [list, cfg] = await Promise.all([getBackups(), getBackupSettings()])
    setBackups(list)
    setSettings(cfg)
    setSettingsDraft(cfg)
  }

  useEffect(() => {
    setLoading(true)
    load()
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить резервные копии'))
      .finally(() => setLoading(false))
  }, [notifyError])

  const patchDraft = (patch: Partial<BackupSettings>) => {
    setSettingsDraft((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  const isSettingsDirty = useMemo(() => {
    if (!settings || !settingsDraft) return false
    return (
      settings.telegram_on_backup !== settingsDraft.telegram_on_backup ||
      settings.auto_backup_enabled !== settingsDraft.auto_backup_enabled ||
      settings.backup_az_enabled !== settingsDraft.backup_az_enabled ||
      settings.auto_backup_days !== settingsDraft.auto_backup_days ||
      settings.retention_count !== settingsDraft.retention_count
    )
  }, [settings, settingsDraft])

  const saveSettingsDraft = async () => {
    if (!settingsDraft) return
    setSavingSettings(true)
    try {
      const updated = await updateBackupSettings({
        telegram_on_backup: settingsDraft.telegram_on_backup,
        auto_backup_enabled: settingsDraft.auto_backup_enabled,
        backup_az_enabled: settingsDraft.backup_az_enabled,
        auto_backup_days: settingsDraft.auto_backup_days,
        retention_count: settingsDraft.retention_count,
      })
      setSettings(updated)
      setSettingsDraft(updated)
      success('Настройки резервного копирования сохранены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSavingSettings(false)
    }
  }

  const stats = useMemo(() => {
    const totalBytes = backups.reduce((sum, b) => sum + b.size_bytes, 0)
    const cfg = settingsDraft ?? settings
    return {
      count: backups.length,
      totalSize: backups.length > 0 ? formatSize(totalBytes) : '—',
      auto: cfg?.auto_backup_enabled ? 'Включена' : 'Выключена',
      retention: cfg ? String(cfg.retention_count) : '—',
    }
  }, [backups, settings, settingsDraft])

  const telegramDeliveryPlan = useMemo(() => {
    const files = ['adminpanelaz_*.tar.gz — AdminPanel (всегда)']
    if (includeAntizapretBackup) {
      files.push('backup-*.tar.gz — AntiZapret (отдельный файл в том же чате)')
    }
    return files
  }, [includeAntizapretBackup])

  const handleSendTelegram = async () => {
    try {
      await withInline(async () => {
        await createBackup(includeConfigs, includeAntizapretBackup, true)
        await load()
      }, 'Создание и отправка в Telegram...')
      success(
        includeAntizapretBackup
          ? 'В Telegram отправлены 2 файла: AdminPanel и AntiZapret'
          : 'В Telegram отправлен 1 файл: AdminPanel',
      )
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отправки в Telegram')
    }
  }

  const handleCreate = async () => {
    try {
      await withInline(async () => {
        await createBackup(includeConfigs, includeAntizapretBackup)
        await load()
      }, 'Создание копии...')
      success('Резервная копия создана')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось создать копию')
    }
  }

  const handleRestore = (fileName: string) => {
    confirm({
      title: 'Восстановить из копии?',
      description: <>Содержимое архива «{fileName}» заменит текущие данные на сервере.</>,
      alert: {
        variant: 'danger',
        title: 'Внимание',
        children: 'Текущие настройки и данные панели будут перезаписаны. После восстановления нужно перезапустить панель.',
      },
      confirmLabel: 'Восстановить',
      destructive: true,
      onConfirm: async () => {
        try {
          await withInline(async () => {
            await restoreBackup(fileName)
            await load()
          }, 'Восстановление...')
          success('Восстановление выполнено — перезапустите панель')
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка восстановления')
        }
      },
    })
  }

  const handleUpload = (restoreAfterUpload: boolean) => {
    pendingRestoreRef.current = restoreAfterUpload
    uploadInputRef.current?.click()
  }

  const handleUploadFileSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    const restoreAfterUpload = pendingRestoreRef.current
    pendingRestoreRef.current = false
    const runUpload = async () => {
      try {
        await withInline(async () => {
          await uploadBackup(file, restoreAfterUpload)
          await load()
        }, restoreAfterUpload ? 'Загрузка и восстановление...' : 'Загрузка архива...')
        success(
          restoreAfterUpload
            ? 'Архив загружен и восстановлен — перезапустите панель'
            : 'Архив загружен и добавлен в список',
        )
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки архива')
      }
    }

    if (restoreAfterUpload) {
      confirm({
        title: 'Загрузить и восстановить?',
        description: (
          <>
            Файл «{file.name}» заменит текущие данные панели на сервере после загрузки.
          </>
        ),
        alert: {
          variant: 'danger',
          title: 'Внимание',
          children:
            'Используйте после переустановки или когда на сервере нет сохранённых копий. После восстановления перезапустите панель.',
        },
        confirmLabel: 'Загрузить и восстановить',
        destructive: true,
        onConfirm: runUpload,
      })
      return
    }

    await runUpload()
  }

  const handleDelete = (fileName: string) => {
    confirm({
      title: 'Удалить архив?',
      description: <>Архив «{fileName}» будет удалён без возможности восстановления.</>,
      confirmLabel: 'Удалить',
      destructive: true,
      onConfirm: async () => {
        try {
          await deleteBackup(fileName)
          await load()
          success('Архив удалён')
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления')
        }
      },
    })
  }

  if (loading) {
    return <Spinner label="Загрузка резервных копий..." className="py-12" />
  }

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <InlineProgressBar active={savingSettings} label="Сохранение настроек..." />

      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 md:col-span-2">
          <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-2xl" />
          <div className="relative grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricPill
              icon={Archive}
              label="Копий"
              value={String(stats.count)}
              tone={stats.count > 0 ? 'default' : 'muted'}
            />
            <MetricPill icon={HardDrive} label="Общий объём" value={stats.totalSize} />
            <MetricPill
              icon={CalendarClock}
              label="Авто-копия"
              value={stats.auto}
              tone={(settingsDraft ?? settings)?.auto_backup_enabled ? 'success' : 'muted'}
            />
            <MetricPill icon={Database} label="Хранить" value={`${stats.retention} шт.`} />
          </div>
        </div>

        <SectionHeading
          title="Создание копии"
          description="AdminPanel и AntiZapret сохраняются по-разному — см. блоки ниже"
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-primary/80 to-primary/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Archive size={18} />
              Создать резервную копию
            </CardTitle>
            <CardDescription>
              Кнопка «Создать копию» всегда делает архив AdminPanel; опции ниже добавляют данные AntiZapret
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <BackupScopeBlock
                icon={LayoutDashboard}
                title="AdminPanel"
                subtitle="Один файл adminpanelaz_*.tar.gz на сервере панели — отображается в списке «Архивы» ниже"
              >
                <div className="space-y-3">
                  <p className="text-xs font-medium text-foreground">Всегда входит в копию:</p>
                  <IncludedItemsList items={ADMIN_PANEL_ALWAYS_INCLUDED} />
                  <OptionCard
                    icon={ListTree}
                    label="Добавить списки маршрутизации AntiZapret"
                    description="include/exclude-hosts и IP-списки с VPN-сервера — в тот же архив AdminPanel, не отдельный файл"
                    checked={includeConfigs}
                    onChange={setIncludeConfigs}
                  />
                </div>
              </BackupScopeBlock>

              <BackupScopeBlock
                icon={Server}
                title="AntiZapret (VPN-сервер)"
                subtitle={
                  includeAntizapretBackup
                    ? 'Отдельный файл на VPN-узле; при отправке в Telegram — второе вложение'
                    : 'Отдельный файл на VPN-узле; сейчас не создаётся и в Telegram не уходит'
                }
              >
                <OptionCard
                  icon={Server}
                  label="Создать полный архив VPN"
                  description="OpenVPN и WireGuard, сертификаты, DNS Knot Resolver и конфиги AntiZapret — восстановление только на VPN-сервере"
                  checked={includeAntizapretBackup}
                  onChange={setIncludeAntizapretBackup}
                />
              </BackupScopeBlock>
            </div>

            {settingsDraft && (
              <div className="space-y-3 rounded-xl border border-dashed bg-muted/10 p-4">
                <div>
                  <p className="text-xs font-medium text-foreground">Telegram</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    В чат уходят <strong className="text-foreground">отдельные файлы</strong> — не один общий архив.
                    Состав зависит от галочек выше.
                  </p>
                </div>
                <ul className="space-y-1 rounded-lg border bg-card/60 px-3 py-2">
                  {telegramDeliveryPlan.map((line) => (
                    <li key={line} className="flex gap-2 text-xs text-muted-foreground">
                      <Send size={12} className="mt-0.5 shrink-0 text-primary" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
                <OptionCard
                  icon={Send}
                  label="Дублировать в Telegram при «Создать копию»"
                  description="Те же файлы, что и при ручной отправке. Нужно сохранить кнопкой «Сохранить настройки»"
                  checked={settingsDraft.telegram_on_backup}
                  onChange={(checked) => patchDraft({ telegram_on_backup: checked })}
                />
              </div>
            )}

            <div className="flex flex-col gap-2 border-t pt-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
              <Button
                variant={isSettingsDirty ? 'default' : 'outline'}
                className="gap-1.5 sm:mr-auto"
                disabled={!isSettingsDirty || savingSettings}
                onClick={() => void saveSettingsDraft()}
              >
                <Save size={16} />
                {savingSettings ? 'Сохранение...' : 'Сохранить настройки'}
              </Button>
              <Button variant="outline" className="gap-1.5" onClick={() => void handleSendTelegram()}>
                <Send size={16} />
                {includeAntizapretBackup
                  ? `Отправить в Telegram (${telegramDeliveryPlan.length} файла)`
                  : 'Отправить в Telegram (1 файл)'}
              </Button>
              <Button onClick={() => void handleCreate()} className="gap-1.5">
                <Archive size={16} />
                Создать копию
              </Button>
            </div>
          </CardContent>
        </Card>

        {settingsDraft && (
          <>
            <SectionHeading
              title="Автоматические копии"
              description="По расписанию: архив AdminPanel на сервере панели и при необходимости отдельный архив на VPN-сервере"
            />

            <Card className="overflow-hidden shadow-sm md:col-span-2">
              <div className="h-1 bg-gradient-to-r from-violet-500/70 to-violet-500/15" />
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <CalendarClock size={18} />
                  Расписание и хранение
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <ToggleRow
                    id="auto-backup"
                    label="Авто-копия AdminPanel"
                    description="База, CIDR и .env панели — файл adminpanelaz_*.tar.gz в списке архивов"
                    checked={settingsDraft.auto_backup_enabled}
                    onCheckedChange={(checked) => patchDraft({ auto_backup_enabled: checked })}
                  />
                  <ToggleRow
                    id="backup-az"
                    label="Плюс полный архив AntiZapret"
                    description="Дополнительно client.sh 8 на VPN-сервере — отдельный файл, не в списке панели"
                    checked={settingsDraft.backup_az_enabled}
                    onCheckedChange={(checked) => patchDraft({ backup_az_enabled: checked })}
                  />
                </div>

                {settingsDraft.auto_backup_enabled && (
                  <div className="grid gap-4 rounded-xl border bg-muted/20 p-4 md:grid-cols-2">
                    <div className="space-y-3">
                      <Label className="text-xs text-muted-foreground">Интервал, дней</Label>
                      <div className="flex flex-wrap gap-2">
                        {INTERVAL_PRESETS.map((d) => (
                          <button
                            key={d}
                            type="button"
                            onClick={() => patchDraft({ auto_backup_days: d })}
                            className={cn(
                              'rounded-lg border px-3 py-1.5 text-sm font-medium transition-all',
                              settingsDraft.auto_backup_days === d
                                ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
                                : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                            )}
                          >
                            {d} дн.
                          </button>
                        ))}
                      </div>
                      <div className="flex items-center gap-2">
                        <Input
                          id="backup-days"
                          type="number"
                          min={1}
                          max={90}
                          className="h-9 w-20"
                          value={settingsDraft.auto_backup_days}
                          onChange={(e) => patchDraft({ auto_backup_days: Number(e.target.value) })}
                        />
                        <span className="text-xs text-muted-foreground">дней</span>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <Label className="text-xs text-muted-foreground">Сколько копий хранить</Label>
                      <div className="flex flex-wrap gap-2">
                        {RETENTION_PRESETS.map((n) => (
                          <button
                            key={n}
                            type="button"
                            onClick={() => patchDraft({ retention_count: n })}
                            className={cn(
                              'rounded-lg border px-3 py-1.5 text-sm font-medium transition-all',
                              settingsDraft.retention_count === n
                                ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
                                : 'hover:border-muted-foreground/30 hover:bg-muted/50',
                            )}
                          >
                            {n}
                          </button>
                        ))}
                      </div>
                      <div className="flex items-center gap-2">
                        <Input
                          id="retention"
                          type="number"
                          min={1}
                          max={30}
                          className="h-9 w-20"
                          value={settingsDraft.retention_count}
                          onChange={(e) => patchDraft({ retention_count: Number(e.target.value) })}
                        />
                        <span className="text-xs text-muted-foreground">копий</span>
                      </div>
                    </div>
                  </div>
                )}

                <div className="flex justify-end border-t pt-4">
                  <Button
                    disabled={!isSettingsDirty || savingSettings}
                    onClick={() => void saveSettingsDraft()}
                    className="gap-1.5"
                  >
                    <Save size={16} />
                    {savingSettings ? 'Сохранение...' : 'Сохранить'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </>
        )}

        <SectionHeading
          title="Архивы AdminPanel"
          description={
            backups.length > 0
              ? `${backups.length} файл${backups.length === 1 ? '' : backups.length < 5 ? 'а' : 'ов'} adminpanelaz_*.tar.gz — полные архивы AntiZapret хранятся на VPN-сервере`
              : 'Только копии панели; архивы AntiZapret создаются на VPN-сервере отдельно'
          }
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-sky-500/70 to-sky-500/15" />
          <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
            <div>
              <CardTitle className="text-base">Сохранённые копии</CardTitle>
              <CardDescription className="mt-1.5">
                Скачивание, загрузка с компьютера, восстановление и удаление архивов
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2 lg:shrink-0">
              <input
                ref={uploadInputRef}
                type="file"
                accept=".tar.gz,.tgz,application/gzip,application/x-gzip"
                className="hidden"
                onChange={(event) => void handleUploadFileSelected(event)}
              />
              <Button variant="outline" size="sm" className="gap-1.5" onClick={() => handleUpload(false)}>
                <Upload size={14} />
                Загрузить
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 border-destructive/30 text-destructive hover:bg-destructive/10"
                onClick={() => handleUpload(true)}
              >
                <RotateCcw size={14} />
                Загрузить и восстановить
              </Button>
              {backups.length > 0 && (
                <Badge variant="secondary" className="shrink-0">
                  {backups.length}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {backups.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-muted-foreground/20 bg-muted/10 px-4 py-10 text-center">
                <ArchiveX className="mb-2 h-8 w-8 text-muted-foreground/70" />
                <p className="text-sm font-medium">Копий пока нет</p>
                <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                  Создайте первую резервную копию или загрузите ранее скачанный архив adminpanelaz_*.tar.gz
                </p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  <Button onClick={() => void handleCreate()} variant="outline" className="gap-1.5">
                    <Archive size={16} />
                    Создать копию
                  </Button>
                  <Button onClick={() => handleUpload(false)} variant="outline" className="gap-1.5">
                    <Upload size={16} />
                    Загрузить архив
                  </Button>
                </div>
              </div>
            ) : (
              <ul className="space-y-2">
                {backups.map((b) => (
                  <li
                    key={b.file_name}
                    className="rounded-xl border bg-card/50 p-3 transition-colors hover:bg-muted/30"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate font-mono text-sm font-medium">{b.file_name}</p>
                          <Badge variant="outline" className="text-[10px]">
                            {formatSize(b.size_bytes)}
                          </Badge>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(b.created_at)}</p>
                        <div className="mt-2 flex flex-wrap gap-1">
                          {b.components.map((c) => (
                            <Badge key={c} variant="secondary" className="text-[10px]">
                              {COMPONENT_LABELS[c] ?? c}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2 lg:shrink-0">
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-1.5"
                          title="Скачать"
                          onClick={async () => {
                            const res = await downloadBackup(b.file_name)
                            if (!res.ok) return notifyError('Ошибка скачивания')
                            const blob = await res.blob()
                            const a = document.createElement('a')
                            a.href = URL.createObjectURL(blob)
                            a.download = b.file_name
                            a.click()
                          }}
                        >
                          <Download size={14} />
                          Скачать
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-1.5"
                          onClick={() => handleRestore(b.file_name)}
                        >
                          <RotateCcw size={14} />
                          Восстановить
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-1.5 border-destructive/30 text-destructive hover:bg-destructive/10"
                          onClick={() => handleDelete(b.file_name)}
                        >
                          <Trash2 size={14} />
                          Удалить
                        </Button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <SettingsAlert variant="info" title="Что восстанавливается откуда" className="md:col-span-2">
          <strong>AdminPanel</strong> — «Восстановить» в списке или «Загрузить и восстановить» для архива с
          компьютера (после переустановки): база, CIDR, .env и при наличии списки маршрутизации.{' '}
          <strong>AntiZapret</strong> — полный архив VPN восстанавливается на VPN-сервере (не через этот список).
        </SettingsAlert>

        <SettingsAlert variant="danger" title="Перед восстановлением AdminPanel" className="md:col-span-2">
          Текущие данные панели будут заменены содержимым выбранного архива. После восстановления перезапустите панель.
        </SettingsAlert>
      </div>
    </div>
  )
}
