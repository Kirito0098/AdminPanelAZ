import { useEffect, useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Gauge,
  Leaf,
  RefreshCw,
  Rocket,
  Save,
  Search,
  Server,
} from 'lucide-react'
import {
  ApiError,
  applyResourceProfile,
  getFeatureToggles,
  getLightHealth,
  getPanelResourceCurrent,
  getPanelResourceHistory,
  getResourceProfiles,
  updateFeatureToggles,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import PanelRestartCard from '@/components/settings/PanelRestartCard'
import { SettingsMetaLine, SettingsToolbar } from '@/components/settings/SettingsChrome'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import {
  buildProfileLiveCopy,
  formatComparedProfileHint,
  formatMeasuredSubtitle,
  summarizePanelResources,
  type PanelResourceSummary,
} from '@/lib/panelResourceStats'
import { cn } from '@/lib/utils'
import type { FeatureToggleItem, ResourceProfileImpact, ResourceProfileItem } from '@/types'

const RESTART_BANNER_KEY = 'featureTogglesPendingRestart'
const RESTART_BANNER_AT_KEY = 'featureTogglesPendingRestartAt'

const PROFILE_META: Record<string, { icon: LucideIcon }> = {
  minimal: { icon: Leaf },
  standard: { icon: Gauge },
  full: { icon: Rocket },
}

function stripPresetRamLine(description: string): string {
  return description.split(';')[0].trim().replace(/\.$/, '')
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

function matchesQuery(item: FeatureToggleItem, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const haystack = [item.label, item.description, item.key, item.env_key, item.resource_impact_label]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return haystack.includes(q)
}

/** Linear/Clerk-style preference row: label + description left, switch right. */
function ModuleToggleRow({
  item,
  enabled,
  onChange,
}: {
  item: FeatureToggleItem
  enabled: boolean
  onChange: (enabled: boolean) => void
}) {
  const switchId = `module-${item.key}`
  return (
    <div
      className={cn(
        'group relative border-b border-border/80 px-1 py-3.5 transition-colors sm:px-2',
        !enabled && 'opacity-90',
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-base',
            enabled ? 'bg-primary/10' : 'bg-muted/70',
          )}
          aria-hidden
        >
          {item.icon}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <label
              htmlFor={switchId}
              className="cursor-pointer text-sm font-medium leading-snug text-foreground"
            >
              {item.label}
            </label>
            {item.resource_impact_level !== 'minimal' && item.resource_impact_level !== 'low' && (
              <Badge
                variant="outline"
                className={cn('h-5 px-1.5 text-[10px] font-normal', impactBadgeClass(item.resource_impact_level))}
              >
                {item.resource_impact_label}
              </Badge>
            )}
          </div>
          <p className="mt-0.5 line-clamp-2 text-sm leading-relaxed text-muted-foreground" title={item.description}>
            {item.description}
          </p>

          {item.key === 'proxy_nodes' && (
            <p className="mt-2 rounded-md border border-amber-500/25 bg-amber-500/8 px-2.5 py-1.5 text-xs text-amber-950 dark:text-amber-100">
              Включайте только если уже установили proxy.sh сами. Панель не ставит и не запускает
              proxy.sh.
            </p>
          )}

          {!enabled && item.disable_hint && (
            <p className="mt-2 text-xs leading-snug text-muted-foreground">{item.disable_hint}</p>
          )}

          {enabled && item.resource_savings && (
            <p className="mt-1.5 line-clamp-1 text-xs text-muted-foreground" title={item.resource_savings}>
              Экономия при выключении: {item.resource_savings}
            </p>
          )}
        </div>

        <Switch
          id={switchId}
          checked={enabled}
          onCheckedChange={onChange}
          className="mt-1 shrink-0"
          aria-label={item.label}
        />
      </div>
    </div>
  )
}

function ProfileCard({
  profile,
  current,
  currentProfileKey,
  applying,
  ramSummary,
  onApply,
}: {
  profile: ResourceProfileItem
  current: boolean
  currentProfileKey: string
  applying: boolean
  ramSummary: PanelResourceSummary | null
  onApply: () => void
}) {
  const meta = PROFILE_META[profile.key] ?? { icon: Server }
  const Icon = meta.icon
  const workers = profile.workers_disabled ?? []
  const liveCopy =
    current && ramSummary?.hasData ? buildProfileLiveCopy(profile, ramSummary) : null
  const description = liveCopy?.description ?? stripPresetRamLine(profile.description)
  const impactRam = liveCopy?.ram ?? profile.impact?.ram
  const impactCpuDisk = liveCopy?.cpuDisk ?? profile.impact?.cpu_disk
  const impactNote = liveCopy?.note ?? profile.impact?.note
  const subtitle =
    current && ramSummary?.hasData
      ? liveCopy?.subtitle ?? formatMeasuredSubtitle(ramSummary)
      : formatComparedProfileHint(profile, ramSummary, currentProfileKey)

  return (
    <button
      type="button"
      disabled={applying || current}
      onClick={onApply}
      className={cn(
        'relative flex h-full w-full flex-col overflow-hidden rounded-xl border p-3 text-left transition-all',
        current
          ? 'cursor-default border-primary/40 bg-primary/5 shadow-sm ring-1 ring-primary/20'
          : 'bg-card/50 hover:border-primary/35 hover:bg-muted/30 disabled:opacity-60',
      )}
    >
      <div className="mb-2 flex shrink-0 items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
              current ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground',
            )}
          >
            <Icon size={16} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold leading-tight">{profile.label}</p>
            {subtitle && <p className="text-[11px] text-primary">{subtitle}</p>}
          </div>
        </div>
        {current ? (
          <Badge variant="default" className="shrink-0 text-[10px]">
            Текущий
          </Badge>
        ) : applying ? (
          <span className="text-[11px] text-muted-foreground">…</span>
        ) : null}
      </div>

      <p className="line-clamp-2 text-xs leading-snug text-muted-foreground">{description}</p>

      {(impactRam || impactCpuDisk || impactNote) && (
        <div className="mt-2 space-y-0.5 text-[11px] leading-snug text-muted-foreground">
          {impactRam && <p className="line-clamp-1">RAM: {impactRam}</p>}
          {impactCpuDisk && <p className="line-clamp-1">CPU/диск: {impactCpuDisk}</p>}
        </div>
      )}

      <div className="mt-2 text-[11px] leading-snug">
        {workers.length > 0 ? (
          <p
            className="line-clamp-2 text-amber-700 dark:text-amber-400"
            title={workers.map(workerLabel).join(', ')}
          >
            Не запускаются: {workers.map(workerLabel).join(', ')}
          </p>
        ) : (
          <p className="text-muted-foreground">Все фоновые задачи включены</p>
        )}
      </div>

      {!current && (
        <span className="mt-2 text-[11px] font-medium text-primary">
          {applying ? 'Применение…' : 'Нажмите, чтобы применить'}
        </span>
      )}
    </button>
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
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [applyingProfile, setApplyingProfile] = useState<string | null>(null)
  const [pendingRestart, setPendingRestart] = useState(
    () => sessionStorage.getItem(RESTART_BANNER_KEY) === '1',
  )
  const [lastImpact, setLastImpact] = useState<ResourceProfileImpact | null>(null)
  const [lastWorkersDisabled, setLastWorkersDisabled] = useState<string[]>([])
  const [ramSummary, setRamSummary] = useState<PanelResourceSummary | null>(null)

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

  const loadPanelRam = async () => {
    try {
      const [history, live] = await Promise.all([
        getPanelResourceHistory('7d'),
        getPanelResourceCurrent(),
      ])
      setRamSummary(summarizePanelResources(history.points, live))
    } catch {
      setRamSummary(null)
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
      void loadPanelRam()
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

  const filteredItems = useMemo(
    () => items.filter((item) => matchesQuery(item, query)),
    [items, query],
  )

  const grouped = useMemo(() => {
    const order = ['background', 'app_module']
    const map = new Map<string, FeatureToggleItem[]>()
    for (const item of filteredItems) {
      const list = map.get(item.group) || []
      list.push(item)
      map.set(item.group, list)
    }
    return order
      .filter((g) => map.has(g))
      .map((g) => [g, map.get(g)!] as const)
      .concat([...map.entries()].filter(([g]) => !order.includes(g)))
  }, [filteredItems])

  const activeProfileMeta = profiles.find((p) => p.key === currentProfile)
  const profileLabel = activeProfileMeta?.label ?? currentProfile

  const enabledCount = Object.values(draft).filter(Boolean).length
  const dirtyCount = items.filter((item) => draft[item.key] !== item.enabled).length
  const dirty = dirtyCount > 0
  const queryActive = query.trim().length > 0

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
    <div className="space-y-4">
      <InlineProgressBar active={saving || applyingProfile !== null} label="Сохранение..." />

      <SettingsToolbar
        title="Разделы панели"
        meta={
          <SettingsMetaLine
            items={[
              { label: 'вкл.', value: enabledCount },
              { label: 'всего модулей', value: items.length },
              { label: 'профиль', value: profileLabel },
            ]}
          />
        }
        actions={
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-9 gap-1.5"
              onClick={() => {
                void load()
                void loadPanelRam()
              }}
              disabled={saving}
            >
              <RefreshCw size={14} />
              Обновить
            </Button>
            <Button
              type="button"
              size="sm"
              className="h-9 gap-1.5"
              onClick={() => void save()}
              disabled={!dirty || saving}
            >
              <Save size={14} />
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </>
        }
      />

      <p className="text-xs text-muted-foreground">
        Замер только стека AdminPanelAZ: панель, node agent и VPN-сервисы локальной ноды
        (OpenVPN, <code className="text-xs">ANTIZAPRET_PATH</code>). Другие проекты на VDS не учитываются.
      </p>

      {pendingRestart && (
        <div className="space-y-3">
          <SettingsAlert variant="warning" title="Перезапустите панель">
            Изменения записаны в <code className="text-xs">backend/.env</code>. Фоновые задачи (трафик, CIDR, метрики)
            подхватятся только после перезапуска сервиса панели.
          </SettingsAlert>
          <div className="flex flex-wrap justify-end gap-2">
            <PanelRestartCard compact onRestartScheduled={clearRestartPending} />
            <Button type="button" size="sm" variant="secondary" onClick={clearRestartPending}>
              Перезапуск выполнен
            </Button>
          </div>
        </div>
      )}

      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Профили ресурсов</CardTitle>
          <CardDescription>
            Быстрые пресеты нагрузки. Minimal и Standard экономят RAM панели; VPN на том же хосте почти не меняется.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            {profiles.map((profile) => (
              <ProfileCard
                key={profile.key}
                profile={profile}
                current={profile.key === currentProfile}
                currentProfileKey={currentProfile}
                applying={applyingProfile === profile.key}
                ramSummary={ramSummary}
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

      <div className="relative">
        <Search
          size={14}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Найти модуль: портал, unlock, трафик…"
          className="h-10 pl-9"
          aria-label="Поиск модулей"
        />
      </div>

      {grouped.length === 0 ? (
        <Card className="shadow-sm">
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Ничего не найдено по запросу «{query.trim()}».
            <button
              type="button"
              className="mt-2 block w-full text-primary hover:underline"
              onClick={() => setQuery('')}
            >
              Сбросить поиск
            </button>
          </CardContent>
        </Card>
      ) : (
        grouped.map(([group, groupItems]) => {
          const enabledInGroup = groupItems.filter((i) => draft[i.key]).length
          return (
            <Card key={group} className="shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-2">
                <div className="min-w-0">
                  <CardTitle className="text-base">
                    {groupItems[0]?.group_meta?.badge || 'Модули'}
                  </CardTitle>
                  <CardDescription className="mt-1">
                    {groupItems[0]?.group_meta?.description ||
                      (group === 'app_module'
                        ? 'Скрывают пункты меню и страницы панели'
                        : 'Работают в фоне — разделы в интерфейсе остаются')}
                  </CardDescription>
                </div>
                <Badge variant="secondary" className="shrink-0 tabular-nums">
                  {enabledInGroup} / {groupItems.length}
                  {queryActive ? '' : ' вкл.'}
                </Badge>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="grid grid-cols-1 gap-x-8 md:grid-cols-2">
                  {groupItems.map((item) => (
                    <ModuleToggleRow
                      key={item.key}
                      item={item}
                      enabled={draft[item.key] ?? false}
                      onChange={(checked) => setDraft((prev) => ({ ...prev, [item.key]: checked }))}
                    />
                  ))}
                </div>
              </CardContent>
            </Card>
          )
        })
      )}

      {dirty && (
        <div className="sticky bottom-2 z-10 flex flex-col-reverse items-stretch gap-2 pb-safe sm:flex-row sm:items-center sm:justify-end">
          <p className="text-center text-xs text-muted-foreground sm:mr-auto sm:text-left">
            Несохранено: {dirtyCount}{' '}
            {dirtyCount === 1 ? 'изменение' : dirtyCount < 5 ? 'изменения' : 'изменений'}
          </p>
          <Button type="button" className="gap-1.5 shadow-lg" onClick={() => void save()} disabled={saving}>
            <Save size={16} />
            {saving ? 'Сохранение...' : 'Сохранить изменения'}
          </Button>
        </div>
      )}
    </div>
  )
}
