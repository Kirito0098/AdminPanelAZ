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
  applyScenarioPreset,
  clearScenarioLocks,
  getFeatureToggles,
  getLightHealth,
  getPanelResourceCurrent,
  getPanelResourceHistory,
  getScenarioPresets,
  previewScenarioPreset,
  updateFeatureToggles,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import PanelRestartCard from '@/components/settings/PanelRestartCard'
import { SettingsMetaLine, SettingsToolbar } from '@/components/settings/SettingsChrome'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import {
  buildProfileLiveCopy,
  formatComparedProfileHint,
  formatMeasuredSubtitle,
  summarizePanelResources,
  type PanelResourceSummary,
} from '@/lib/panelResourceStats'
import { parseTimestamp } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type {
  FeatureToggleItem,
  ScenarioPresetImpact,
  ScenarioPresetItem,
  ScenarioPresetPreview,
  ScenarioResolved,
} from '@/types'

const RESTART_BANNER_KEY = 'featureTogglesPendingRestart'
const RESTART_BANNER_AT_KEY = 'featureTogglesPendingRestartAt'

const PRESET_META: Record<string, { icon: LucideIcon }> = {
  panel_only: { icon: Leaf },
  home: { icon: Gauge },
  commercial: { icon: Rocket },
}

/** «Клиенты» и «Пользователи (абоненты)» не выключаются одновременно. */
const CORE_UI_MODULES = ['clients_page', 'user_provisioning'] as const

function isLastEnabledCoreModule(key: string, draft: Record<string, boolean>): boolean {
  if (!CORE_UI_MODULES.includes(key as (typeof CORE_UI_MODULES)[number])) return false
  const other = key === 'clients_page' ? 'user_provisioning' : 'clients_page'
  return Boolean(draft[key]) && !(draft[other] ?? false)
}

function stripPresetRamLine(description: string): string {
  return description.split(';')[0].trim().replace(/\.$/, '')
}

function parseIsoMs(value: string | null | undefined): number | null {
  return parseTimestamp(value)?.getTime() ?? null
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
  disabledSwitch,
  blockHint,
}: {
  item: FeatureToggleItem
  enabled: boolean
  onChange: (enabled: boolean) => void
  disabledSwitch?: boolean
  blockHint?: string
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
          {disabledSwitch && blockHint && (
            <p className="mt-2 rounded-md border border-amber-500/25 bg-amber-500/8 px-2.5 py-1.5 text-xs text-amber-950 dark:text-amber-100">
              {blockHint}
            </p>
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
          onCheckedChange={disabledSwitch ? undefined : onChange}
          disabled={disabledSwitch}
          className="mt-1 shrink-0"
          aria-label={item.label}
        />
      </div>
    </div>
  )
}

function PresetCard({
  preset,
  current,
  currentPresetKey,
  applying,
  ramSummary,
  onApply,
}: {
  preset: ScenarioPresetItem
  current: boolean
  currentPresetKey: string
  applying: boolean
  ramSummary: PanelResourceSummary | null
  onApply: () => void
}) {
  const meta = PRESET_META[preset.key] ?? { icon: Server }
  const Icon = meta.icon
  const workers = preset.workers_disabled ?? []
  const liveCopy =
    current && ramSummary?.hasData ? buildProfileLiveCopy(preset, ramSummary) : null
  const description = liveCopy?.description ?? stripPresetRamLine(preset.description)
  const impactRam = liveCopy?.ram ?? preset.impact?.ram
  const impactCpuDisk = liveCopy?.cpuDisk ?? preset.impact?.cpu_disk
  const impactNote = liveCopy?.note ?? preset.impact?.note
  const subtitle =
    current && ramSummary?.hasData
      ? liveCopy?.subtitle ?? formatMeasuredSubtitle(ramSummary)
      : formatComparedProfileHint(preset, ramSummary, currentPresetKey)

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
            <p className="text-sm font-semibold leading-tight">{preset.label}</p>
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

      {preset.required_labels && preset.required_labels.length > 0 && (
        <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
          Обязательные: {preset.required_labels.join(', ')}
        </p>
      )}

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

/** Diff-подсказка перед применением сценария: точный список включаемых/выключаемых модулей. */
function PresetDiff({ preview }: { preview: ScenarioPresetPreview }) {
  const grace = preview.settings_changes?.inactive_user_grace_period_months
  return (
    <div className="space-y-2 text-sm">
      {preview.will_enable.length > 0 && (
        <div>
          <p className="font-medium">Включится</p>
          <p className="text-muted-foreground">{preview.will_enable.join(', ')}</p>
        </div>
      )}
      {preview.will_disable.length > 0 && (
        <div>
          <p className="font-medium">Выключится</p>
          <p className="text-muted-foreground">{preview.will_disable.join(', ')}</p>
        </div>
      )}
      {preview.required_labels && preview.required_labels.length > 0 && (
        <div>
          <p className="font-medium">Обязательные (нельзя будет отключить)</p>
          <p className="text-muted-foreground">{preview.required_labels.join(', ')}</p>
        </div>
      )}
      {grace && (
        <p className="text-muted-foreground">
          Льготный период неактивных пользователей: {grace.from} → {grace.to} мес.
        </p>
      )}
      {preview.will_enable.length === 0 && preview.will_disable.length === 0 && !grace && (
        <p className="text-muted-foreground">
          Модули уже соответствуют сценарию — изменения не требуются.
        </p>
      )}
    </div>
  )
}

function ImpactSummary({
  impact,
  workers,
}: {
  impact: ScenarioPresetImpact | null | undefined
  workers: string[]
}) {
  if (!impact && workers.length === 0) return null
  return (
    <div className="rounded-xl border bg-muted/15 p-4 text-sm">
      <p className="mb-2 font-medium">Экономия после применения сценария</p>
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
  const { confirm, dialogProps } = useConfirmDialog()
  const [items, setItems] = useState<FeatureToggleItem[]>([])
  const [presets, setPresets] = useState<ScenarioPresetItem[]>([])
  const [resolved, setResolved] = useState<ScenarioResolved | null>(null)
  const [draft, setDraft] = useState<Record<string, boolean>>({})
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [applyingPreset, setApplyingPreset] = useState<string | null>(null)
  const [unlinking, setUnlinking] = useState(false)
  const [pendingRestart, setPendingRestart] = useState(
    () => sessionStorage.getItem(RESTART_BANNER_KEY) === '1',
  )
  const [lastImpact, setLastImpact] = useState<ScenarioPresetImpact | null>(null)
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
      const [data, presetData] = await Promise.all([getFeatureToggles(), getScenarioPresets()])
      setItems(data.items)
      setDraft(Object.fromEntries(data.items.map((item) => [item.key, item.enabled])))
      setPresets(presetData.items)
      setResolved(presetData.resolved)
      await syncRestartBanner()
      void loadPanelRam()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить модули')
    } finally {
      setLoading(false)
    }
  }

  /** Пересчитывает вычисленный сценарий («Кастомный» / активный пресет) по текущим модулям. */
  const refreshPresetState = async () => {
    try {
      const presetData = await getScenarioPresets()
      setPresets(presetData.items)
      setResolved(presetData.resolved)
    } catch {
      // бейдж сценария не критичен — молча оставляем предыдущее значение
    }
  }

  /** Сценарий никогда не применяется сразу: сначала показываем diff и ждём подтверждения. */
  const requestApply = async (preset: string) => {
    try {
      const preview = await previewScenarioPreset(preset)
      confirm({
        title: `Применить сценарий «${preview.label}»?`,
        description: preview.summary_ru,
        confirmLabel: 'Применить',
        children: <PresetDiff preview={preview} />,
        onConfirm: async () => {
          setApplyingPreset(preview.preset)
          try {
            const result = await applyScenarioPreset(preview.preset)
            setPresets(result.presets.items)
            setResolved(result.presets.resolved)
            setLastImpact(result.impact ?? null)
            setLastWorkersDisabled(result.workers_disabled ?? [])
            const data = await getFeatureToggles()
            setItems(data.items)
            setDraft(Object.fromEntries(data.items.map((item) => [item.key, item.enabled])))
            await refreshModules()
            markRestartPending()
            success(
              `Сценарий «${preview.label}» применён. Перезапустите панель для фоновых задач.`,
            )
          } catch (err) {
            notifyError(err instanceof ApiError ? err.message : 'Не удалось применить сценарий')
          } finally {
            setApplyingPreset(null)
          }
        },
      })
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось получить diff сценария')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  /** Снимает обязательные ограничения сценария, не меняя ни один модуль. */
  const unlinkScenario = async () => {
    setUnlinking(true)
    try {
      const presetData = await clearScenarioLocks()
      setPresets(presetData.items)
      setResolved(presetData.resolved)
      const data = await getFeatureToggles()
      setItems(data.items)
      setDraft(Object.fromEntries(data.items.map((item) => [item.key, item.enabled])))
      await refreshModules()
      success('Ограничения сняты: обязательные модули больше не заблокированы.')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось снять ограничения')
    } finally {
      setUnlinking(false)
    }
  }

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

  const currentPresetKey = resolved && !resolved.is_custom ? resolved.key : ''
  const activePresetMeta = presets.find((p) => p.key === currentPresetKey)
  const resetTarget = resolved?.last_applied || resolved?.based_on || ''

  const enabledCount = Object.values(draft).filter(Boolean).length
  const dirtyCount = items.filter((item) => draft[item.key] !== item.enabled).length
  const dirty = dirtyCount > 0
  const queryActive = query.trim().length > 0

  const save = async () => {
    setSaving(true)
    try {
      const coreOff = CORE_UI_MODULES.every((key) => !(draft[key] ?? false))
      if (coreOff) {
        notifyError(
          'Нельзя отключить «Клиенты» и «Пользователи (абоненты)» одновременно. ' +
            'Оставьте хотя бы один из этих разделов включённым.',
        )
        return
      }
      const updates = Object.fromEntries(
        items.filter((item) => draft[item.key] !== item.enabled).map((item) => [item.key, draft[item.key]]),
      )
      const data = await updateFeatureToggles(updates)
      setItems(data.items)
      setDraft(Object.fromEntries(data.items.map((item) => [item.key, item.enabled])))
      // Ручная правка модулей меняет вычисленный сценарий: «Кастомный» должен появиться сразу.
      await refreshPresetState()
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
      <InlineProgressBar active={saving || applyingPreset !== null} label="Сохранение..." />

      <SettingsToolbar
        title="Разделы панели"
        meta={
          <SettingsMetaLine
            items={[
              { label: 'вкл.', value: enabledCount },
              { label: 'всего модулей', value: items.length },
              { label: 'сценарий', value: resolved?.badge_label ?? '—' },
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
          <CardTitle className="text-base">Сценарии</CardTitle>
          <CardDescription>
            Быстрые пресеты нагрузки: «Только панель» (без локального AntiZapret), «Домашнее» и
            «Коммерческое». VPN на том же хосте почти не меняется.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {resolved?.is_custom && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2">
              <Badge variant="outline" className="text-[11px] font-normal">
                {resolved.badge_label}
              </Badge>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8"
                disabled={!resetTarget || applyingPreset !== null}
                onClick={() => void requestApply(resetTarget)}
              >
                Сбросить к пресету
              </Button>
            </div>
          )}
          {resolved?.locks_active && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-primary/25 bg-primary/5 px-3 py-2">
              <p className="text-xs text-muted-foreground">
                Сценарий «{resolved.is_custom ? resolved.base_label ?? resolved.label : resolved.label}»:
                обязательные модули
                {resolved.required_labels?.length
                  ? ` (${resolved.required_labels.join(', ')})`
                  : ''}{' '}
                нельзя отключить, пока действуют ограничения.
              </p>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8"
                disabled={unlinking || applyingPreset !== null}
                onClick={() => void unlinkScenario()}
              >
                {unlinking ? 'Снятие...' : 'Снять ограничения'}
              </Button>
            </div>
          )}
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            {presets.map((preset) => (
              <PresetCard
                key={preset.key}
                preset={preset}
                current={preset.key === currentPresetKey}
                currentPresetKey={currentPresetKey}
                applying={applyingPreset === preset.key}
                ramSummary={ramSummary}
                onApply={() => void requestApply(preset.key)}
              />
            ))}
          </div>
          {pendingRestart && (lastImpact || activePresetMeta?.impact || lastWorkersDisabled.length > 0) && (
            <ImpactSummary
              impact={lastImpact ?? activePresetMeta?.impact}
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
                  {groupItems.map((item) => {
                    const coreBlocked = isLastEnabledCoreModule(item.key, draft)
                    const lockedByScenario = Boolean(item.locked && (draft[item.key] ?? false))
                    return (
                      <ModuleToggleRow
                        key={item.key}
                        item={item}
                        enabled={draft[item.key] ?? false}
                        onChange={(checked) => setDraft((prev) => ({ ...prev, [item.key]: checked }))}
                        disabledSwitch={coreBlocked || lockedByScenario}
                        blockHint={
                          coreBlocked
                            ? 'Нельзя выключить «Клиенты» и «Пользователи (абоненты)» одновременно — оставьте хотя бы один из этих разделов включённым.'
                            : lockedByScenario
                              ? item.lock_reason ??
                                'Модуль заблокирован сценарием или правилом протоколов.'
                              : undefined
                        }
                      />
                    )
                  })}
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

      <ConfirmDialogHost dialogProps={dialogProps} />
    </div>
  )
}
