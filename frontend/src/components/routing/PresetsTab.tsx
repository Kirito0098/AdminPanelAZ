import { useCallback, useEffect, useMemo, useState } from 'react'
import { Layers, Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react'
import {
  ApiError,
  createCidrDbPreset,
  deleteCidrDbPreset,
  getCidrDbPresets,
  resetCidrDbPreset,
  updateCidrDbPreset,
} from '@/api/client'
import AppDialog from '@/components/shared/AppDialog'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useNotifications } from '@/context/NotificationContext'
import type { CidrDbPresetInfo, CidrPresetSettings, CidrProviderInfo } from '@/types'

const REGION_SCOPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'all', label: 'Все регионы' },
  { value: 'europe', label: 'Европа' },
  { value: 'north-america', label: 'Северная Америка' },
  { value: 'asia-pacific', label: 'Азия и Тихий океан' },
  { value: 'middle-east', label: 'Ближний Восток' },
]

const defaultSettings = (): CidrPresetSettings => ({
  region_scopes: ['all'],
  include_non_geo_fallback: false,
  exclude_ru_cidrs: false,
})

interface PresetsTabProps {
  providers: CidrProviderInfo[]
  isAdmin: boolean
  actionLoading: boolean
  onApply: (preset: CidrDbPresetInfo) => void
}

export default function PresetsTab({
  providers,
  isAdmin,
  actionLoading,
  onApply,
}: PresetsTabProps) {
  const { success, error: notifyError } = useNotifications()
  const [presets, setPresets] = useState<CidrDbPresetInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<CidrDbPresetInfo | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<CidrDbPresetInfo | null>(null)
  const [confirmReset, setConfirmReset] = useState<CidrDbPresetInfo | null>(null)

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedProviders, setSelectedProviders] = useState<string[]>([])
  const [settings, setSettings] = useState<CidrPresetSettings>(defaultSettings())

  const loadPresets = useCallback(async () => {
    setLoading(true)
    try {
      const { presets: list } = await getCidrDbPresets()
      setPresets(list)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки пресетов')
    } finally {
      setLoading(false)
    }
  }, [notifyError])

  useEffect(() => {
    void loadPresets()
  }, [loadPresets])

  const providerName = useCallback(
    (filename: string, preset?: CidrDbPresetInfo) =>
      preset?.providers_meta?.[filename]?.name ??
      providers.find((p) => p.filename === filename)?.name ??
      filename,
    [providers],
  )

  const sortedProviders = useMemo(
    () => [...providers].sort((a, b) => a.name.localeCompare(b.name, 'ru')),
    [providers],
  )

  const openCreate = () => {
    setEditing(null)
    setName('')
    setDescription('')
    setSelectedProviders([])
    setSettings(defaultSettings())
    setFormOpen(true)
  }

  const openEdit = (preset: CidrDbPresetInfo) => {
    setEditing(preset)
    setName(preset.name)
    setDescription(preset.description)
    setSelectedProviders([...preset.providers])
    setSettings({ ...preset.settings })
    setFormOpen(true)
  }

  const toggleProvider = (filename: string) => {
    setSelectedProviders((prev) =>
      prev.includes(filename) ? prev.filter((f) => f !== filename) : [...prev, filename],
    )
  }

  const toggleScope = (scope: string) => {
    setSettings((prev) => {
      if (scope === 'all') {
        return { ...prev, region_scopes: ['all'] }
      }
      const withoutAll = prev.region_scopes.filter((s) => s !== 'all')
      const next = withoutAll.includes(scope)
        ? withoutAll.filter((s) => s !== scope)
        : [...withoutAll, scope]
      return { ...prev, region_scopes: next.length ? next : ['all'] }
    })
  }

  const handleSave = async () => {
    const trimmedName = name.trim()
    if (!trimmedName) {
      notifyError('Введите название пресета')
      return
    }
    if (selectedProviders.length === 0) {
      notifyError('Выберите хотя бы одного провайдера')
      return
    }

    setSaving(true)
    try {
      const payload = {
        name: trimmedName,
        description: description.trim(),
        providers: selectedProviders,
        settings,
      }
      if (editing) {
        await updateCidrDbPreset(editing.id, payload)
        success('Пресет обновлён')
      } else {
        await createCidrDbPreset(payload)
        success('Пресет создан')
      }
      setFormOpen(false)
      await loadPresets()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения пресета')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) return
    setSaving(true)
    try {
      await deleteCidrDbPreset(confirmDelete.id)
      success('Пресет удалён')
      setConfirmDelete(null)
      await loadPresets()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления пресета')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    if (!confirmReset) return
    setSaving(true)
    try {
      await resetCidrDbPreset(confirmReset.id)
      success('Пресет сброшен к умолчанию')
      setConfirmReset(null)
      await loadPresets()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сброса пресета')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (presets.length === 0) {
    return (
      <div className="space-y-4">
        <EmptyState
          icon={Layers}
          title="Нет пресетов"
          description="Встроенные пресеты маршрутизации не найдены. Запустите seed или создайте свой пресет."
        />
        {isAdmin && (
          <Button size="sm" onClick={openCreate}>
            <Plus size={14} className="mr-1" />
            Создать пресет
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {isAdmin && (
        <div className="flex justify-end">
          <Button size="sm" onClick={openCreate} disabled={saving}>
            <Plus size={14} className="mr-1" />
            Создать пресет
          </Button>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {presets.map((preset) => (
          <Card key={preset.id} className="flex flex-col">
            <CardHeader>
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Layers size={16} className="text-primary shrink-0" />
                  {preset.name}
                </CardTitle>
                <Badge variant={preset.is_builtin ? 'secondary' : 'outline'} className="shrink-0 text-xs">
                  {preset.is_builtin ? 'Встроенный' : 'Пользовательский'}
                </Badge>
              </div>
              <CardDescription>{preset.description || 'Без описания'}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-3">
              <div className="flex flex-wrap gap-1.5">
                {preset.providers.slice(0, 8).map((f) => (
                  <Badge key={f} variant="outline" className="text-xs">
                    {providerName(f, preset)}
                  </Badge>
                ))}
                {preset.providers.length > 8 && (
                  <Badge variant="outline" className="text-xs">
                    +{preset.providers.length - 8}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {preset.providers.length} провайдер(ов)
              </p>
              <div className="mt-auto flex flex-wrap items-center gap-2">
                {isAdmin && (
                  <Button
                    size="sm"
                    disabled={actionLoading}
                    onClick={() => onApply(preset)}
                  >
                    Применить
                  </Button>
                )}
                {isAdmin && preset.is_builtin && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={saving}
                    onClick={() => setConfirmReset(preset)}
                  >
                    <RotateCcw size={14} className="mr-1" />
                    Сбросить
                  </Button>
                )}
                {isAdmin && !preset.is_builtin && (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={saving}
                      onClick={() => openEdit(preset)}
                    >
                      <Pencil size={14} className="mr-1" />
                      Изменить
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-destructive hover:text-destructive"
                      disabled={saving}
                      onClick={() => setConfirmDelete(preset)}
                    >
                      <Trash2 size={14} className="mr-1" />
                      Удалить
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <AppDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        title={editing ? 'Редактировать пресет' : 'Новый пресет'}
        description="Сохраните набор провайдеров и настроек геофильтра как пресет."
        size="lg"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setFormOpen(false)} disabled={saving}>
              Отмена
            </Button>
            <Button onClick={() => void handleSave()} disabled={saving}>
              {saving ? 'Сохранение...' : 'Сохранить'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="preset-name">Название</Label>
            <Input
              id="preset-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Мой пресет"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="preset-desc">Описание</Label>
            <Textarea
              id="preset-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Необязательно"
            />
          </div>
          <div className="space-y-2">
            <Label>Провайдеры</Label>
            <div className="max-h-48 overflow-y-auto rounded-md border p-3 space-y-2">
              {sortedProviders.map((p) => (
                <label key={p.filename} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-input"
                    checked={selectedProviders.includes(p.filename)}
                    onChange={() => toggleProvider(p.filename)}
                  />
                  <span>{p.name}</span>
                  <span className="text-xs text-muted-foreground">{p.filename}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <Label>Регионы</Label>
            <div className="flex flex-wrap gap-3">
              {REGION_SCOPE_OPTIONS.map((opt) => (
                <label key={opt.value} className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded border-input"
                    checked={settings.region_scopes.includes(opt.value)}
                    onChange={() => toggleScope(opt.value)}
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                className="rounded border-input"
                checked={settings.include_non_geo_fallback}
                onChange={(e) =>
                  setSettings((prev) => ({ ...prev, include_non_geo_fallback: e.target.checked }))
                }
              />
              Включать non-geo fallback
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                className="rounded border-input"
                checked={settings.exclude_ru_cidrs}
                onChange={(e) =>
                  setSettings((prev) => ({ ...prev, exclude_ru_cidrs: e.target.checked }))
                }
              />
              Исключать RU CIDR
            </label>
          </div>
        </div>
      </AppDialog>

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
        title="Удалить пресет?"
        description={confirmDelete ? `Пресет «${confirmDelete.name}» будет удалён безвозвратно.` : ''}
        confirmLabel="Удалить"
        destructive
        loading={saving}
        onConfirm={handleDelete}
      />

      <ConfirmDialog
        open={!!confirmReset}
        onOpenChange={(open) => !open && setConfirmReset(null)}
        title="Сбросить пресет?"
        description={
          confirmReset
            ? `Пресет «${confirmReset.name}» будет восстановлен до встроенных значений.`
            : ''
        }
        confirmLabel="Сбросить"
        loading={saving}
        onConfirm={handleReset}
      />
    </div>
  )
}
