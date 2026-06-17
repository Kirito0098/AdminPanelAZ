import {
  ApiError,
  applyRouting,
  getAntizapretSettings,
  updateAntizapretSettings,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import EmptyState from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import Spinner from '@/components/ui/Spinner'
import { Switch } from '@/components/ui/switch'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { cn } from '@/lib/utils'
import type { AntizapretSettingField } from '@/types'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowRight,
  Ban,
  Cable,
  Cloud,
  Globe,
  ListFilter,
  Network,
  Play,
  RefreshCw,
  Route,
  Save,
  Server,
  Settings2,
  Shield,
} from 'lucide-react'
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

type FieldLayout = 'list' | 'grid'

/** Строки сетки: левый и правый блок на одной линии. */
const LAYOUT_ROWS: ReadonlyArray<{ left?: string; right?: string }> = [
  { left: 'Маршрутизация трафика', right: 'Безопасность сервера' },
  { left: 'Резервные порты', right: 'Cloudflare WARP' },
  { left: 'Очистка списков', right: 'AdBlock' },
]
const LAYOUT_BOTTOM = ['Адреса подключения'] as const

const PLACED_SECTIONS = new Set<string>([
  ...LAYOUT_ROWS.flatMap((row) => [row.left, row.right].filter((title): title is string => Boolean(title))),
  ...LAYOUT_BOTTOM,
])

const FIELD_DISPLAY: Partial<Record<string, { title: string; description: string }>> = {
  openvpn_host: {
    title: 'OpenVPN',
    description: 'Домен или IP-адрес для клиентских конфигов OpenVPN',
  },
  wireguard_host: {
    title: 'WireGuard / AmneziaWG',
    description: 'Домен или IP-адрес для клиентских конфигов WireGuard и AmneziaWG',
  },
}

const FIELD_SECTIONS: {
  title: string
  description?: string
  keys: string[]
  icon: LucideIcon
  fieldLayout?: FieldLayout
}[] = [
  {
    title: 'Маршрутизация трафика',
    description: 'Какие сервисы направлять через AntiZapret VPN',
    icon: Route,
    keys: [
      'route_all',
      'discord_include',
      'cloudflare_include',
      'telegram_include',
      'whatsapp_include',
      'roblox_include',
    ],
  },
  {
    title: 'Безопасность сервера',
    description: 'Защита VPN-сервера от атак и злоупотреблений',
    icon: Shield,
    keys: [
      'ssh_protection',
      'attack_protection',
      'scan_protection',
      'torrent_guard',
      'restrict_forward',
    ],
  },
  {
    title: 'Резервные порты',
    description: 'Альтернативные порты OpenVPN и WireGuard/AmneziaWG для обхода блокировок',
    icon: Network,
    keys: ['OPENVPN_BACKUP_TCP', 'OPENVPN_BACKUP_UDP', 'WIREGUARD_BACKUP'],
  },
  {
    title: 'Cloudflare WARP',
    description: 'Отправка трафика через Cloudflare WARP',
    icon: Cloud,
    keys: ['ANTIZAPRET_WARP', 'VPN_WARP'],
  },
  {
    title: 'AdBlock',
    description: 'Блокировка рекламы и трекеров в VPN-трафике',
    icon: Ban,
    keys: ['block_ads'],
  },
  {
    title: 'Адреса подключения',
    description: 'Домены, которые попадают в клиентские конфиги VPN',
    icon: Cable,
    fieldLayout: 'grid',
    keys: ['openvpn_host', 'wireguard_host'],
  },
  {
    title: 'Очистка списков',
    description: 'Фильтрация доменов при авто-обновлении списков маршрутизации',
    icon: ListFilter,
    keys: ['clear_hosts'],
  },
]

function fieldDisplay(field: AntizapretSettingField) {
  const override = FIELD_DISPLAY[field.key]
  return {
    title: override?.title || field.title || field.key,
    description: override?.description || field.description,
  }
}

function isFlagOn(value: string | undefined): boolean {
  return value?.toLowerCase() === 'y'
}

function groupSchema(schema: AntizapretSettingField[]) {
  const byKey = new Map(schema.map((field) => [field.key, field]))
  const used = new Set<string>()
  const sections = FIELD_SECTIONS.map((section) => {
    const fields = section.keys
      .map((key) => byKey.get(key))
      .filter((field): field is AntizapretSettingField => Boolean(field))
    fields.forEach((field) => used.add(field.key))
    return { ...section, fields }
  }).filter((section) => section.fields.length > 0)

  const rest = schema.filter((field) => !used.has(field.key))
  if (rest.length > 0) {
    sections.push({
      title: 'Другие параметры',
      description: 'Дополнительные настройки setup',
      icon: Settings2,
      keys: [],
      fields: rest,
    })
  }
  return sections
}

function indexSectionsByTitle(sections: ReturnType<typeof groupSchema>) {
  return new Map(sections.map((section) => [section.title, section]))
}

function sectionEnabledCount(fields: AntizapretSettingField[], draft: Record<string, string>) {
  const flags = fields.filter((field) => field.type === 'flag')
  const enabled = flags.filter((field) => isFlagOn(draft[field.key])).length
  return { enabled, total: flags.length }
}

function FlagSettingRow({
  field,
  value,
  dirty,
  disabled,
  onChange,
}: {
  field: AntizapretSettingField
  value: string
  dirty: boolean
  disabled: boolean
  onChange: (value: string) => void
}) {
  const id = field.html_id || field.key
  const enabled = isFlagOn(value)
  const display = fieldDisplay(field)

  return (
    <div
      className={cn(
        'flex items-start justify-between gap-4 px-4 py-3.5 transition-colors sm:px-5',
        dirty && 'bg-amber-500/5',
        !disabled && 'hover:bg-muted/30',
      )}
    >
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Label htmlFor={id} className="cursor-pointer font-medium leading-snug">
            {display.title}
          </Label>
          {dirty && (
            <Badge
              variant="outline"
              className="border-amber-500/40 px-1.5 py-0 text-[10px] text-amber-700 dark:text-amber-300"
            >
              изменено
            </Badge>
          )}
        </div>
        {display.description && (
          <p className="text-xs leading-relaxed text-muted-foreground">{display.description}</p>
        )}
        <p className="font-mono text-[10px] text-muted-foreground/70">
          {field.param_label || field.env}
        </p>
      </div>
      <Switch
        id={id}
        checked={enabled}
        disabled={disabled}
        className="mt-0.5"
        aria-label={`${display.title}: ${enabled ? 'включено' : 'выключено'}`}
        onCheckedChange={(checked) => onChange(checked ? 'y' : 'n')}
      />
    </div>
  )
}

function StringSettingRow({
  field,
  value,
  dirty,
  disabled,
  onChange,
}: {
  field: AntizapretSettingField
  value: string
  dirty: boolean
  disabled: boolean
  onChange: (value: string) => void
}) {
  const id = field.html_id || field.key
  const display = fieldDisplay(field)

  return (
    <div className={cn('space-y-2 px-4 py-4 sm:px-5', dirty && 'bg-amber-500/5')}>
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Label htmlFor={id}>{display.title}</Label>
          {dirty && (
            <Badge
              variant="outline"
              className="border-amber-500/40 px-1.5 py-0 text-[10px] text-amber-700 dark:text-amber-300"
            >
              изменено
            </Badge>
          )}
        </div>
        {display.description && (
          <p className="text-xs text-muted-foreground">{display.description}</p>
        )}
        <p className="font-mono text-[10px] text-muted-foreground/70">
          {field.param_label || field.env}
        </p>
      </div>
      <Input
        id={id}
        value={value}
        disabled={disabled}
        placeholder={field.env}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

type GroupedSection = ReturnType<typeof groupSchema>[number]

function ConfigSectionCard({
  section,
  draft,
  dirtySet,
  disabled,
  onDraftChange,
}: {
  section: GroupedSection
  draft: Record<string, string>
  dirtySet: Set<string>
  disabled: boolean
  onDraftChange: (key: string, value: string) => void
}) {
  const SectionIcon = section.icon
  const { enabled, total } = sectionEnabledCount(section.fields, draft)
  const useGrid =
    section.fieldLayout === 'grid' &&
    section.fields.length > 1 &&
    section.fields.every((field) => field.type === 'string')

  return (
    <Card id={`section-${section.title}`} className="flex h-full flex-col overflow-hidden">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <SectionIcon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <CardTitle className="text-base">{section.title}</CardTitle>
              {section.description && (
                <CardDescription className="mt-1">{section.description}</CardDescription>
              )}
              {section.title === 'Cloudflare WARP' && (
                <Link
                  to="/warper"
                  className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary underline-offset-4 hover:underline"
                >
                  Управление AZ-WARP
                  <ArrowRight className="h-3 w-3" />
                </Link>
              )}
            </div>
          </div>
          {total > 0 && (
            <Badge variant="secondary" className="shrink-0 tabular-nums">
              {enabled}/{total}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col p-0">
        <div
          className={cn(
            'flex flex-1 flex-col border-t',
            useGrid
              ? 'grid sm:grid-cols-2 sm:divide-x divide-y sm:divide-y-0'
              : 'divide-y',
          )}
        >
          {section.fields.map((field) =>
            field.type === 'flag' ? (
              <FlagSettingRow
                key={field.key}
                field={field}
                value={draft[field.key] ?? ''}
                dirty={dirtySet.has(field.key)}
                disabled={disabled}
                onChange={(value) => onDraftChange(field.key, value)}
              />
            ) : (
              <StringSettingRow
                key={field.key}
                field={field}
                value={draft[field.key] ?? ''}
                dirty={dirtySet.has(field.key)}
                disabled={disabled}
                onChange={(value) => onDraftChange(field.key, value)}
              />
            ),
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function WorkflowStep({
  step,
  label,
  active,
  done,
}: {
  step: number
  label: string
  active: boolean
  done: boolean
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-full border px-3 py-1 text-xs transition-colors',
        done && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
        active && !done && 'border-primary/40 bg-primary/10 font-medium text-primary',
        !active && !done && 'border-transparent bg-muted/60 text-muted-foreground',
      )}
    >
      <span
        className={cn(
          'flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold',
          done && 'bg-emerald-500 text-white',
          active && !done && 'bg-primary text-primary-foreground',
          !active && !done && 'bg-muted-foreground/20 text-muted-foreground',
        )}
      >
        {done ? '✓' : step}
      </span>
      {label}
    </div>
  )
}

export default function AntizapretConfigTab() {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()

  const [schema, setSchema] = useState<AntizapretSettingField[]>([])
  const [saved, setSaved] = useState<Record<string, string>>({})
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [nodeName, setNodeName] = useState<string | null>(null)

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [applying, setApplying] = useState(false)
  const [needsApply, setNeedsApply] = useState(false)
  const [applyOpen, setApplyOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getAntizapretSettings()
      setSchema(data.schema)
      setSaved(data.settings)
      setDraft(data.settings)
      setNodeName(data.node_name ?? activeNode?.name ?? null)
      setNeedsApply(false)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Не удалось загрузить настройки AntiZapret'
      setLoadError(message)
      notifyError(message)
    } finally {
      setLoading(false)
    }
  }, [activeNode?.name, notifyError])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  const sections = useMemo(() => groupSchema(schema), [schema])
  const sectionsByTitle = useMemo(() => indexSectionsByTitle(sections), [sections])
  const extraSections = useMemo(
    () => sections.filter((section) => !PLACED_SECTIONS.has(section.title)),
    [sections],
  )

  const dirtyKeys = useMemo(
    () => schema.filter((field) => draft[field.key] !== saved[field.key]).map((field) => field.key),
    [schema, draft, saved],
  )
  const dirty = dirtyKeys.length > 0
  const dirtySet = useMemo(() => new Set(dirtyKeys), [dirtyKeys])

  const renderSection = (title: string) => {
    const section = sectionsByTitle.get(title)
    if (!section) return null
    return (
      <ConfigSectionCard
        key={section.title}
        section={section}
        draft={draft}
        dirtySet={dirtySet}
        disabled={saving || applying}
        onDraftChange={(key, value) => setDraft((prev) => ({ ...prev, [key]: value }))}
      />
    )
  }

  const enabledFlags = useMemo(
    () => schema.filter((field) => field.type === 'flag' && isFlagOn(draft[field.key])).length,
    [schema, draft],
  )

  const save = async () => {
    if (!dirty) return
    setSaving(true)
    try {
      const updates = Object.fromEntries(dirtyKeys.map((key) => [key, draft[key]]))
      const result = await updateAntizapretSettings(updates)
      const refreshed = await getAntizapretSettings()
      setSaved(refreshed.settings)
      setDraft(refreshed.settings)
      setNeedsApply(result.needs_apply)
      success(result.message)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения настроек')
    } finally {
      setSaving(false)
    }
  }

  const apply = async () => {
    setApplying(true)
    try {
      const resp = await applyRouting()
      trackBackgroundTask(resp.task_id, {
        onComplete: () => {
          setNeedsApply(false)
          success(resp.message || 'Маршрутизация применена (doall.sh)')
          setApplyOpen(false)
        },
        onError: (task, message) => {
          notifyError(task?.error || task?.message || message)
        },
      })
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка применения конфигурации')
    } finally {
      setApplying(false)
    }
  }

  const resetDraft = () => {
    setDraft(saved)
  }

  if (loading) {
    return <Spinner label="Загрузка конфигурации AntiZapret..." className="py-12" />
  }

  if (loadError) {
    return (
      <div className="space-y-4">
        <SettingsAlert variant="danger" title="Ошибка загрузки">
          {loadError}
        </SettingsAlert>
        <Button type="button" variant="secondary" onClick={() => void load()}>
          <RefreshCw className="mr-1.5 h-4 w-4" />
          Повторить
        </Button>
      </div>
    )
  }

  if (schema.length === 0) {
    return (
      <EmptyState
        icon={Settings2}
        title="Нет параметров конфигурации"
        description="API не вернул схему настроек AntiZapret."
      />
    )
  }

  const pendingApply = needsApply && !dirty
  const step1Active = dirty
  const step1Done = pendingApply
  const step2Active = dirty
  const step2Done = pendingApply
  const step3Active = pendingApply
  const step3Done = false

  return (
    <div className="space-y-6">
      <InlineProgressBar active={saving} label="Сохранение настроек..." />
      <InlineProgressBar active={applying} label="Применение doall.sh..." />

      <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-card via-card to-muted/30 p-5 shadow-sm">
        <div className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-primary/5" />
        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Globe className="h-6 w-6" />
            </div>
            <div className="min-w-0">
              <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">Конфиг AntiZapret</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Параметры файла{' '}
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">setup</span> на
                активном узле
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {nodeName && (
                  <Badge variant="outline" className="gap-1.5">
                    <Server className="h-3 w-3" />
                    {nodeName}
                  </Badge>
                )}
                <Badge variant="secondary">{schema.length} параметров</Badge>
                <Badge variant="default">{enabledFlags} вкл.</Badge>
                {dirty && (
                  <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-300">
                    {dirtyKeys.length} несохранённых
                  </Badge>
                )}
                {needsApply && !dirty && (
                  <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-300">
                    ждёт doall.sh
                  </Badge>
                )}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => void load()}
              disabled={saving || applying}
            >
              <RefreshCw className="mr-1.5 h-4 w-4" />
              Обновить
            </Button>
            {dirty && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={resetDraft}
                disabled={saving || applying}
              >
                Сбросить
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              onClick={() => void save()}
              disabled={!dirty || saving || applying}
            >
              <Save className="mr-1.5 h-4 w-4" />
              Сохранить
            </Button>
            <Button
              type="button"
              size="sm"
              variant="default"
              onClick={() => setApplyOpen(true)}
              disabled={saving || applying || dirty}
            >
              <Play className="mr-1.5 h-4 w-4" />
              Применить
            </Button>
          </div>
        </div>

        <div className="relative mt-5 flex flex-wrap items-center gap-2 border-t pt-4">
          <span className="mr-1 text-xs text-muted-foreground">Шаги:</span>
          <WorkflowStep step={1} label="Изменить" active={step1Active} done={step1Done} />
          <ArrowRight className="hidden h-3.5 w-3.5 text-muted-foreground/50 sm:block" />
          <WorkflowStep step={2} label="Сохранить" active={step2Active} done={step2Done} />
          <ArrowRight className="hidden h-3.5 w-3.5 text-muted-foreground/50 sm:block" />
          <WorkflowStep step={3} label="doall.sh" active={step3Active} done={step3Done} />
        </div>
      </div>

      {(dirty || needsApply) && (
        <div
          className={cn(
            'sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/90',
            dirty ? 'border-amber-500/30 bg-amber-500/5' : 'border-amber-500/30 bg-background/95',
          )}
        >
          <p className="text-sm">
            {dirty ? (
              <>Есть несохранённые изменения ({dirtyKeys.length}). Сохраните перед применением.</>
            ) : (
              <>Настройки сохранены — осталось выполнить doall.sh на узле.</>
            )}
          </p>
          <div className="flex flex-wrap gap-2">
            {dirty ? (
              <>
                <Button type="button" variant="ghost" size="sm" onClick={resetDraft} disabled={saving || applying}>
                  Сбросить
                </Button>
                <Button type="button" size="sm" onClick={() => void save()} disabled={saving || applying}>
                  <Save className="mr-1.5 h-4 w-4" />
                  Сохранить
                </Button>
              </>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={() => setApplyOpen(true)}
                disabled={saving || applying}
              >
                <Play className="mr-1.5 h-4 w-4" />
                Применить doall.sh
              </Button>
            )}
          </div>
        </div>
      )}

      {needsApply && !dirty && (
        <SettingsAlert variant="warning" title="Требуется применение">
          Настройки записаны на узел, но ещё не активированы. Нажмите «Применить», чтобы выполнить
          doall.sh.
        </SettingsAlert>
      )}

      <div className="grid gap-5 lg:grid-cols-2 lg:items-stretch">
        {LAYOUT_ROWS.map((row, index) => (
          <Fragment key={`layout-row-${index}`}>
            <div className="min-w-0">
              {row.left ? renderSection(row.left) : null}
            </div>
            <div className="min-w-0">
              {row.right ? renderSection(row.right) : null}
            </div>
          </Fragment>
        ))}
      </div>

      <div className="mt-5 space-y-5">
        {LAYOUT_BOTTOM.map((title) => renderSection(title))}
        {extraSections.map((section) => (
          <ConfigSectionCard
            key={section.title}
            section={section}
            draft={draft}
            dirtySet={dirtySet}
            disabled={saving || applying}
            onDraftChange={(key, value) => setDraft((prev) => ({ ...prev, [key]: value }))}
          />
        ))}
      </div>

      <ConfirmDialog
        open={applyOpen}
        onOpenChange={setApplyOpen}
        title="Применить конфигурацию AntiZapret?"
        description="Будет выполнен doall.sh на активном узле. Это может занять несколько минут и перезагрузить правила маршрутизации."
        confirmLabel="Выполнить doall.sh"
        destructive
        loading={applying}
        onConfirm={() => void apply()}
        alert={{
          variant: 'warning',
          title: 'Длительная операция',
          children: 'Не закрывайте вкладку до завершения doall.sh.',
        }}
      />
    </div>
  )
}
