import { useEffect, useMemo, useState } from 'react'
import { Puzzle, RefreshCw, Save } from 'lucide-react'
import { ApiError, getFeatureToggles, updateFeatureToggles } from '@/api/client'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import type { FeatureToggleItem } from '@/types'

export default function FeatureTogglesTab() {
  const { refresh: refreshModules } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const [items, setItems] = useState<FeatureToggleItem[]>([])
  const [draft, setDraft] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getFeatureToggles()
      setItems(data.items)
      setDraft(Object.fromEntries(data.items.map((item) => [item.key, item.enabled])))
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить модули')
    } finally {
      setLoading(false)
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
      <InlineProgressBar active={saving} label="Сохранение модулей..." />

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
