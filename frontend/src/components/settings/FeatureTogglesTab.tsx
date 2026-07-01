import { useEffect, useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Cpu,
  Gauge,
  Leaf,
  Puzzle,
  RefreshCw,
  Rocket,
  Save,
  Server,
  ToggleLeft,
} from 'lucide-react'
import {
  ApiError,
  applyResourceProfile,
  getFeatureToggles,
  getLightHealth,
  getResourceProfiles,
  updateFeatureToggles,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import type { FeatureToggleItem, ResourceProfileImpact, ResourceProfileItem } from '@/types'

const RESTART_BANNER_KEY = 'featureTogglesPendingRestart'
const RESTART_BANNER_AT_KEY = 'featureTogglesPendingRestartAt'

const PROFILE_META: Record<string, { icon: LucideIcon; stripe: string }> = {
  minimal: {
    icon: Leaf,
    stripe: 'from-emerald-500/70 to-emerald-500/15',
  },
  standard: {
    icon: Gauge,
    stripe: 'from-primary/80 to-primary/15',
  },
  full: {
    icon: Rocket,
    stripe: 'from-violet-500/70 to-violet-500/15',
  },
}

function formatRamHint(gb: number | null | undefined): string | null {
  if (gb == null) return null
  return `ориентир ~${gb} GB RAM`
}

const GROUP_STRIPE: Record<string, string> = {
  background: 'from-sky-500/70 to-sky-500/15',
  app_module: 'from-violet-500/70 to-violet-500/15',
}

function parseIsoMs(value: string | null | undefined): number | null {
  if (!value) return null
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? null : ms
}

function workerLabel(key: string): string {
  const labels: Record<string, string> = {
    traffic_collector: 'Сбор трафика',
    node_health: 'Опрос узлов',
    resource_metrics: 'Метрики VPN-узлов',
    panel_resource_metrics: 'Метрики панели',
    cidr_scheduler: 'Планировщик CIDR',
    cert_sync: 'Синхронизация сертификатов',
    resource_monitor: 'Монитор CPU/RAM',
  }
  return labels[key] || key
}

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
  tone?: 'default' | 'success' | 'muted' | 'warning'
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card/80 p-3 shadow-sm backdrop-blur-sm">
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          tone === 'success' && 'bg-primary/15 text-primary',
          tone === 'warning' && 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
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

function impactBadgeClass(level: string) {
  switch (level) {
    case 'high':
      return 'border-amber-500/40 bg-amber-500/10 text-amber-800 dark:text-amber-200'
    case 'medium':
      return 'border-orange-500/30 bg-orange-500/10 text-orange-800 dark:text-orange-200'
    case 'minimal':
      return 'border-muted-foreground/20 bg-muted/50 text-muted-foreground'
    default:
      return ''
  }
}

function ModuleToggleCard({
  item,
  enabled,
  onChange,
}: {
  item: FeatureToggleItem
  enabled: boolean
  onChange: (enabled: boolean) => void
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3 rounded-xl border p-4 transition-all',
        enabled ? 'border-primary/25 bg-primary/5 shadow-sm' : 'bg-card/50',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          <div
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg',
              enabled ? 'bg-primary/15' : 'bg-muted/80',
            )}
            aria-hidden
          >
            {item.icon}
          </div>
          <div className="min-w-0">
            <p className="font-medium leading-tight">{item.label}</p>
            <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">{item.env_key}</p>
          </div>
        </div>
        <Badge variant="outline" className={cn('shrink-0 text-[10px]', impactBadgeClass(item.resource_impact_level))}>
          {item.resource_impact_label}
        </Badge>
      </div>

      <p className="text-sm leading-relaxed text-muted-foreground">{item.description}</p>

      {item.resource_savings && (
        <p className="text-xs text-muted-foreground">Экономия: {item.resource_savings}</p>
      )}

      <div className="flex items-center justify-between gap-3 border-t pt-3">
        <div className="flex items-center gap-2">
          <Switch id={`module-${item.key}`} checked={enabled} onCheckedChange={onChange} />
          <Label htmlFor={`module-${item.key}`} className="cursor-pointer text-sm">
            {enabled ? 'Включён' : 'Выключен'}
          </Label>
        </div>
        <Badge variant={enabled ? 'default' : 'secondary'} className="text-[10px]">
          {enabled ? 'Вкл.' : 'Выкл.'}
        </Badge>
      </div>

      {!enabled && item.disable_hint && (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-100">
          {item.disable_hint}
        </p>
      )}
    </div>
  )
}

function ProfileCard({
  profile,
  current,
  applying,
  onApply,
}: {
  profile: ResourceProfileItem
  current: boolean
  applying: boolean
  onApply: () => void
}) {
  const meta = PROFILE_META[profile.key] ?? {
    icon: Server,
    stripe: 'from-muted to-muted/15',
  }
  const Icon = meta.icon
  const ramHint = formatRamHint(profile.recommended_ram_gb)
  const workers = profile.workers_disabled ?? []

  return (
    <div
      className={cn(
        'relative flex h-full flex-col overflow-hidden rounded-xl border transition-all',
        current ? 'border-primary/40 bg-primary/5 shadow-sm ring-1 ring-primary/20' : 'bg-card/50 hover:border-primary/30',
      )}
    >
      <div className={cn('h-1 shrink-0 bg-gradient-to-r', meta.stripe)} />
      <div className="flex flex-1 flex-col p-3">
        <div className="mb-2 flex shrink-0 items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
                current ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground',
              )}
            >
              <Icon size={18} />
            </div>
            <div className="min-w-0">
              <p className="font-semibold leading-tight">{profile.label}</p>
              {ramHint && <p className="text-xs text-muted-foreground">{ramHint}</p>}
            </div>
          </div>
          {current && (
            <Badge variant="default" className="shrink-0 text-[10px]">
              Текущий
            </Badge>
          )}
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          <p className="line-clamp-2 text-sm leading-snug text-muted-foreground">{profile.description}</p>

          {profile.impact && (profile.impact.ram || profile.impact.cpu_disk || profile.impact.note) && (
            <div className="mt-2 space-y-0.5 rounded-lg border bg-muted/20 px-2.5 py-1.5 text-xs leading-snug text-muted-foreground">
              {profile.impact.ram && <p className="line-clamp-1">RAM: {profile.impact.ram}</p>}
              {profile.impact.cpu_disk && <p className="line-clamp-1">CPU/диск: {profile.impact.cpu_disk}</p>}
              {profile.impact.note && <p className="line-clamp-1 text-foreground/80">{profile.impact.note}</p>}
            </div>
          )}

          <div className="mt-2 text-xs leading-snug">
            {workers.length > 0 ? (
              <p className="line-clamp-2 text-amber-700 dark:text-amber-400" title={workers.map(workerLabel).join(', ')}>
                Не запускаются: {workers.map(workerLabel).join(', ')}
              </p>
            ) : (
              <p className="text-muted-foreground">Все фоновые задачи включены</p>
            )}
          </div>

          <div className="flex-1" aria-hidden />
        </div>

        <Button
          type="button"
          size="sm"
          className="mt-2 w-full shrink-0"
          variant={current ? 'secondary' : 'default'}
          disabled={applying || current}
          onClick={onApply}
        >
          {applying ? 'Применение…' : current ? 'Активен' : 'Применить'}
        </Button>
      </div>
    </div>
  )
}

function ImpactSummary({
  impact,
  workers,
}: {
  impact: ResourceProfileImpact | null | undefined
  workers: string[]
}) {
  if (!impact && workers.length === 0) return null
  return (
    <div className="rounded-xl border bg-muted/15 p-4 text-sm">
      <p className="mb-2 font-medium">Экономия после применения профиля</p>
      <div className="space-y-1 text-muted-foreground">
        {impact?.ram && <p>RAM: {impact.ram}</p>}
        {impact?.cpu_disk && <p>CPU/диск: {impact.cpu_disk}</p>}
        {impact?.note && <p>{impact.note}</p>}
        {workers.length > 0 && <p>Отключённые задачи: {workers.map(workerLabel).join(', ')}</p>}
      </div>
    </div>
  )
}

export default function FeatureTogglesTab() {
  const { refresh: refreshModules } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const [items, setItems] = useState<FeatureToggleItem[]>([])
  const [profiles, setProfiles] = useState<ResourceProfileItem[]>([])
  const [currentProfile, setCurrentProfile] = useState('standard')
  const [draft, setDraft] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [applyingProfile, setApplyingProfile] = useState<string | null>(null)
  const [pendingRestart, setPendingRestart] = useState(
    () => sessionStorage.getItem(RESTART_BANNER_KEY) === '1',
  )
  const [lastImpact, setLastImpact] = useState<ResourceProfileImpact | null>(null)
  const [lastWorkersDisabled, setLastWorkersDisabled] = useState<string[]>([])

  const markRestartPending = () => {
    sessionStorage.setItem(RESTART_BANNER_KEY, '1')
    sessionStorage.setItem(RESTART_BANNER_AT_KEY, new Date().toISOString())
    setPendingRestart(true)
  }

  const clearRestartPending = () => {
    sessionStorage.removeItem(RESTART_BANNER_KEY)
    sessionStorage.removeItem(RESTART_BANNER_AT_KEY)
    setPendingRestart(false)
  }

  const syncRestartBanner = async () => {
    if (sessionStorage.getItem(RESTART_BANNER_KEY) !== '1') return
    const pendingAtMs = parseIsoMs(sessionStorage.getItem(RESTART_BANNER_AT_KEY))
    if (pendingAtMs == null) return
    try {
      const health = await getLightHealth()
      const startedAtMs = parseIsoMs(health.started_at)
      if (startedAtMs != null && startedAtMs >= pendingAtMs) {
        clearRestartPending()
      }
    } catch {
      // health check is best-effort
    }
  }

  const load = async () => {
    setLoading(true)
    try {
      const [data, profileData] = await Promise.all([getFeatureToggles(), getResourceProfiles()])
      setItems(data.items)
      setDraft(Object.fromEntries(data.items.map((item) => [item.key, item.enabled])))
      setProfiles(profileData.items)
      setCurrentProfile(profileData.current_profile)
      await syncRestartBanner()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить модули')
    } finally {
      setLoading(false)
    }
  }

  const applyProfile = async (profile: string) => {
    setApplyingProfile(profile)
    try {
      const result = await applyResourceProfile(profile)
      setCurrentProfile(result.profile)
      setProfiles(result.profiles.items)
      setLastImpact(result.impact ?? null)
      setLastWorkersDisabled(result.workers_disabled ?? [])
      const data = await getFeatureToggles()
      setItems(data.items)
      setDraft(Object.fromEntries(data.items.map((item) => [item.key, item.enabled])))
      await refreshModules()
      markRestartPending()
      success(`Профиль «${profile}» применён. Перезапустите панель для фоновых задач.`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось применить профиль')
    } finally {
      setApplyingProfile(null)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const grouped = useMemo(() => {
    const order = ['background', 'app_module']
    const map = new Map<string, FeatureToggleItem[]>()
    for (const item of items) {
      const list = map.get(item.group) || []
      list.push(item)
      map.set(item.group, list)
    }
    return order
      .filter((g) => map.has(g))
      .map((g) => [g, map.get(g)!] as const)
      .concat(
        [...map.entries()].filter(([g]) => !order.includes(g)),
      )
  }, [items])

  const activeProfileMeta = profiles.find((p) => p.key === currentProfile)
  const profileLabel = activeProfileMeta?.label ?? currentProfile

  const enabledCount = Object.values(draft).filter(Boolean).length
  const dirty = items.some((item) => draft[item.key] !== item.enabled)

  const save = async () => {
    setSaving(true)
    try {
      const updates = Object.fromEntries(
        items.filter((item) => draft[item.key] !== item.enabled).map((item) => [item.key, draft[item.key]]),
      )
      const data = await updateFeatureToggles(updates)
      setItems(data.items)
      setDraft(Object.fromEntries(data.items.map((item) => [item.key, item.enabled])))
      await refreshModules()
      markRestartPending()
      success('Модули сохранены. Перезапустите панель для применения фоновых задач.')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения модулей')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <Spinner label="Загрузка модулей..." className="py-12" />
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 md:items-start">
      <InlineProgressBar active={saving || applyingProfile !== null} label="Сохранение..." className="md:col-span-2" />

      <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 md:col-span-2">
        <div className="pointer-events-none absolute -left-6 top-0 h-28 w-28 rounded-full bg-emerald-500/10 blur-2xl" />
        <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-violet-500/10 blur-2xl" />
        <div className="relative space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Puzzle size={18} className="text-primary" />
                Разделы и фоновые задачи
              </div>
              <p className="max-w-2xl text-sm text-muted-foreground">
                Включайте только нужные функции. На 1–2 GB весь функционал обычно работает стабильно; профили ниже —
                ориентир, если на том же сервере ещё и VPN.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => void load()} disabled={saving}>
                <RefreshCw size={14} />
                Обновить
              </Button>
              <Button
                type="button"
                size="sm"
                className="gap-1.5"
                onClick={() => void save()}
                disabled={!dirty || saving}
              >
                <Save size={14} />
                {saving ? 'Сохранение...' : 'Сохранить'}
              </Button>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricPill
              icon={PROFILE_META[currentProfile]?.icon ?? Gauge}
              label="Профиль"
              value={profileLabel}
              tone={currentProfile === 'minimal' ? 'success' : 'default'}
            />
            <MetricPill icon={ToggleLeft} label="Включено" value={String(enabledCount)} tone="success" />
            <MetricPill icon={Cpu} label="Всего модулей" value={String(items.length)} />
            <MetricPill
              icon={Server}
              label="Выключено"
              value={String(items.length - enabledCount)}
              tone={items.length - enabledCount > 0 ? 'muted' : 'default'}
            />
          </div>
        </div>
      </div>

      {pendingRestart && (
        <div className="space-y-3 md:col-span-2">
          <SettingsAlert variant="warning" title="Перезапустите панель">
            Изменения записаны в <code className="text-xs">backend/.env</code>. Фоновые задачи (трафик, CIDR, метрики)
            подхватятся только после перезапуска сервиса панели.
          </SettingsAlert>
          <div className="flex justify-end">
            <Button type="button" size="sm" variant="secondary" onClick={clearRestartPending}>
              Перезапуск выполнен
            </Button>
          </div>
        </div>
      )}

      <SectionHeading
        title="Профили ресурсов"
        description="Готовые пресеты для VDS с разным объёмом памяти — переключают сразу несколько модулей"
      />

      <Card className="overflow-hidden shadow-sm md:col-span-2">
        <div className="h-1 bg-gradient-to-r from-emerald-500/70 via-primary/50 to-violet-500/70" />
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Режим экономии</CardTitle>
          <CardDescription>
            Пресеты для разной нагрузки: Minimal экономит ресурсы, Full включает всё — в том числе на 1–2 GB, если
            панель не делит память с тяжёлым VPN на том же хосте
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3 md:items-stretch">
            {profiles.map((profile) => (
              <ProfileCard
                key={profile.key}
                profile={profile}
                current={profile.key === currentProfile}
                applying={applyingProfile === profile.key}
                onApply={() => void applyProfile(profile.key)}
              />
            ))}
          </div>
          {pendingRestart && (lastImpact || activeProfileMeta?.impact || lastWorkersDisabled.length > 0) && (
            <ImpactSummary
              impact={lastImpact ?? activeProfileMeta?.impact}
              workers={lastWorkersDisabled}
            />
          )}
        </CardContent>
      </Card>

      {grouped.map(([group, groupItems]) => (
        <div key={group} className="contents">
          <SectionHeading
            title={groupItems[0]?.group_meta?.label || group}
            description={groupItems[0]?.group_meta?.description || ''}
          />
          <Card className="overflow-hidden shadow-sm md:col-span-2">
            <div className={cn('h-1 bg-gradient-to-r', GROUP_STRIPE[group] ?? 'from-muted to-muted/15')} />
            <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
              <div>
                <CardTitle className="text-base">
                  {groupItems[0]?.group_meta?.badge || 'Модули'}
                </CardTitle>
                <CardDescription className="mt-1.5">
                  {group === 'app_module'
                    ? 'Скрывают пункты меню и страницы панели'
                    : 'Работают в фоне — разделы в интерфейсе остаются'}
                </CardDescription>
              </div>
              <Badge variant="secondary" className="shrink-0">
                {groupItems.filter((i) => draft[i.key]).length} / {groupItems.length} вкл.
              </Badge>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2">
                {groupItems.map((item) => (
                  <ModuleToggleCard
                    key={item.key}
                    item={item}
                    enabled={draft[item.key] ?? false}
                    onChange={(checked) => setDraft((prev) => ({ ...prev, [item.key]: checked }))}
                  />
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      ))}

      {dirty && (
        <div className="sticky bottom-2 z-10 flex justify-end md:col-span-2">
          <Button type="button" className="gap-1.5 shadow-lg" onClick={() => void save()} disabled={saving}>
            <Save size={16} />
            {saving ? 'Сохранение...' : 'Сохранить изменения'}
          </Button>
        </div>
      )}
    </div>
  )
}
