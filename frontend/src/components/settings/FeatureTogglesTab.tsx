import { useEffect, useMemo, useState } from 'react'
import { Puzzle, RefreshCw, Save } from 'lucide-react'
import { ApiError, applyResourceProfile, getFeatureToggles, getResourceProfiles, updateFeatureToggles } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import type { FeatureToggleItem, ResourceProfileImpact, ResourceProfileItem } from '@/types'

const RESTART_BANNER_KEY = 'featureTogglesPendingRestart'

function workerLabel(key: string): string {
  const labels: Record<string, string> = {
    traffic_collector: 'Сбор трафика',
    node_health: 'Опрос узлов',
    resource_metrics: 'Метрики VPN-узлов',
    panel_resource_metrics: 'Метрики панели',
    cidr_scheduler: 'CIDR scheduler',
    cert_sync: 'Синхронизация сертификатов',
    resource_monitor: 'CPU/RAM monitor',
  }
  return labels[key] || key
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
    setPendingRestart(true)
  }

  const load = async () => {
    setLoading(true)
    try {
      const [data, profileData] = await Promise.all([getFeatureToggles(), getResourceProfiles()])
      setItems(data.items)
      setDraft(Object.fromEntries(data.items.map((item) => [item.key, item.enabled])))
      setProfiles(profileData.items)
      setCurrentProfile(profileData.current_profile)
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
    const map = new Map<string, FeatureToggleItem[]>()
    for (const item of items) {
      const list = map.get(item.group) || []
      list.push(item)
      map.set(item.group, list)
    }
    return map
  }, [items])

  const activeProfileMeta = profiles.find((p) => p.key === currentProfile)

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
    <div className="space-y-4">
      <InlineProgressBar active={saving || applyingProfile !== null} label="Сохранение модулей..." />

      {pendingRestart && (
        <SettingsAlert variant="warning" title="Перезапустите панель">
          Изменения профиля или модулей записаны в <code className="text-xs">backend/.env</code>. Фоновые задачи
          (traffic, CIDR, metrics) подхватятся только после перезапуска сервиса панели.
        </SettingsAlert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Resource profiles</CardTitle>
          <CardDescription>
            Пресеты для VDS с разным объёмом RAM. Minimal отключает traffic sync, metrics collectors, CIDR scheduler и
            опрос узлов.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          {profiles.map((profile) => (
            <div key={profile.key} className="rounded-lg border p-3">
              <div className="mb-1 flex items-center justify-between gap-2">
                <div className="font-medium">{profile.label}</div>
                {profile.key === currentProfile && <Badge variant="default">Текущий</Badge>}
              </div>
              <p className="mb-2 text-xs text-muted-foreground">{profile.description}</p>
              {profile.recommended_ram_gb != null && (
                <p className="mb-2 text-xs text-muted-foreground">Рекомендуется: {profile.recommended_ram_gb} GB RAM</p>
              )}
              {profile.impact && (
                <div className="mb-3 space-y-1 text-xs text-muted-foreground">
                  {profile.impact.ram && <p>RAM: {profile.impact.ram}</p>}
                  {profile.impact.cpu_disk && <p>CPU/диск: {profile.impact.cpu_disk}</p>}
                  {profile.impact.note && <p>{profile.impact.note}</p>}
                </div>
              )}
              {(profile.workers_disabled?.length ?? 0) > 0 && (
                <p className="mb-3 text-xs text-amber-700 dark:text-amber-400">
                  Не запускаются: {profile.workers_disabled!.map(workerLabel).join(', ')}
                </p>
              )}
              <Button
                type="button"
                size="sm"
                variant={profile.key === currentProfile ? 'secondary' : 'default'}
                disabled={applyingProfile !== null || profile.key === currentProfile}
                onClick={() => void applyProfile(profile.key)}
              >
                {applyingProfile === profile.key ? 'Применение…' : 'Применить'}
              </Button>
            </div>
          ))}
        </CardContent>
        {(lastImpact || activeProfileMeta?.impact) && pendingRestart && (
          <CardContent className="border-t pt-4 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">Экономия после применения</p>
            {(lastImpact?.ram || activeProfileMeta?.impact?.ram) && (
              <p>RAM: {lastImpact?.ram ?? activeProfileMeta?.impact?.ram}</p>
            )}
            {(lastImpact?.cpu_disk || activeProfileMeta?.impact?.cpu_disk) && (
              <p>CPU/диск: {lastImpact?.cpu_disk ?? activeProfileMeta?.impact?.cpu_disk}</p>
            )}
            {lastWorkersDisabled.length > 0 && (
              <p>Отключённые workers: {lastWorkersDisabled.map(workerLabel).join(', ')}</p>
            )}
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Puzzle className="h-5 w-5" />
              Модули и задачи
            </CardTitle>
            <CardDescription>
              Управление фоновыми задачами и разделами панели через `.env` (AdminAntizapret 1.9.0).
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={() => void load()} disabled={saving}>
              <RefreshCw className="mr-1 h-4 w-4" />
              Обновить
            </Button>
            <Button type="button" size="sm" onClick={() => void save()} disabled={!dirty || saving}>
              <Save className="mr-1 h-4 w-4" />
              Сохранить
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="mb-4 flex flex-wrap gap-2 text-sm">
            <Badge variant="secondary">Всего: {items.length}</Badge>
            <Badge variant="default">Включено: {enabledCount}</Badge>
            <Badge variant="outline">Выключено: {items.length - enabledCount}</Badge>
          </div>
        </CardContent>
      </Card>

      {[...grouped.entries()].map(([group, groupItems]) => (
        <Card key={group}>
          <CardHeader>
            <CardTitle className="text-base">{groupItems[0]?.group_meta?.label || group}</CardTitle>
            <CardDescription>{groupItems[0]?.group_meta?.description}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            {groupItems.map((item) => (
              <div key={item.key} className="rounded-lg border p-3">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium">
                      {item.icon} {item.label}
                    </div>
                    <div className="text-xs text-muted-foreground">{item.env_key}</div>
                  </div>
                  <Badge variant="outline">{item.resource_impact_label}</Badge>
                </div>
                <p className="mb-3 text-sm text-muted-foreground">{item.description}</p>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant={draft[item.key] ? 'default' : 'secondary'}
                    onClick={() => setDraft((prev) => ({ ...prev, [item.key]: true }))}
                  >
                    Включён
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={!draft[item.key] ? 'destructive' : 'secondary'}
                    onClick={() => setDraft((prev) => ({ ...prev, [item.key]: false }))}
                  >
                    Выключен
                  </Button>
                </div>
                {!draft[item.key] && item.disable_hint && (
                  <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">{item.disable_hint}</p>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
