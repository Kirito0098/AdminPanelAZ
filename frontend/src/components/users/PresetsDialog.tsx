import { useEffect, useMemo, useState } from 'react'
import { Layers, Loader2, Plus, Save, Trash2 } from 'lucide-react'
import { getNodes, getNodeSyncGroups } from '@/api/nodes'
import { createPreset, deletePreset, listPresets, updatePreset } from '@/api/users'
import { REQUEST_PROTOCOLS } from '@/lib/accessRequests'
import { formatBytes } from '@/lib/trafficFormat'
import { protocolLabel } from '@/lib/vpnTypes'
import AppDialog from '@/components/shared/AppDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Spinner from '@/components/ui/Spinner'
import { Switch } from '@/components/ui/switch'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import type { Node, PresetBase, PresetResponse } from '@/types'

const GB = 1024 ** 3

interface PresetsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface PresetForm {
  name: string
  node_ids: number[]
  protocols: string[]
  config_count: string
  access_days: string
  traffic_gb: string
  config_quota: string
  is_default: boolean
}

const EMPTY_FORM: PresetForm = {
  name: '',
  node_ids: [],
  protocols: [],
  config_count: '1',
  access_days: '',
  traffic_gb: '',
  config_quota: '',
  is_default: false,
}

function formFromPreset(preset: PresetResponse): PresetForm {
  return {
    name: preset.name,
    node_ids: [...preset.node_ids],
    protocols: [...preset.protocols],
    config_count: String(preset.config_count ?? 1),
    access_days: preset.access_days != null ? String(preset.access_days) : '',
    traffic_gb:
      preset.traffic_limit_bytes != null ? String(preset.traffic_limit_bytes / GB) : '',
    config_quota: preset.config_quota != null ? String(preset.config_quota) : '',
    is_default: preset.is_default,
  }
}

function presetMeta(preset: PresetResponse, nodes: Node[]): string {
  const nodeNames = preset.node_ids
    .map((id) => nodes.find((node) => node.id === id)?.name)
    .filter(Boolean)
  const parts = [
    nodeNames.length ? `узлы: ${nodeNames.join(', ')}` : 'без узлов',
    preset.protocols.length
      ? `протоколы: ${preset.protocols.map((p) => protocolLabel(p)).join(', ')}`
      : 'без протоколов',
    `${preset.config_count} конф.`,
    preset.access_days != null ? `${preset.access_days} дн.` : 'без срока',
    preset.traffic_limit_bytes ? `лимит ${formatBytes(preset.traffic_limit_bytes)}` : null,
    preset.config_quota != null ? `квота ${preset.config_quota}` : null,
  ].filter(Boolean)
  return parts.join(' · ')
}

export default function PresetsDialog({ open, onOpenChange }: PresetsDialogProps) {
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const [presets, setPresets] = useState<PresetResponse[]>([])
  const [nodes, setNodes] = useState<Node[]>([])
  const [replicaIds, setReplicaIds] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState<PresetForm | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<PresetResponse | null>(null)

  const availableProtocols = useMemo(
    () => REQUEST_PROTOCOLS.filter((p) => p.featureKeys.some((key) => isEnabled(key))),
    [isEnabled],
  )
  const assignableNodes = useMemo(
    () => nodes.filter((node) => (node.node_kind ?? 'vpn') === 'vpn' && !replicaIds.has(node.id)),
    [nodes, replicaIds],
  )

  const reload = async () => {
    setLoading(true)
    try {
      setPresets(await listPresets())
    } catch {
      /* список пуст — покажем заглушку */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!open) return
    void reload()
    let cancelled = false
    void Promise.all([getNodes(), getNodeSyncGroups().catch(() => [])])
      .then(([list, groups]) => {
        if (cancelled) return
        const replicas = new Set<number>()
        for (const group of groups) {
          for (const id of group.replica_node_ids ?? []) replicas.add(id)
        }
        setNodes(list)
        setReplicaIds(replicas)
      })
      .catch(() => {
        if (!cancelled) setNodes([])
      })
    return () => {
      cancelled = true
    }
  }, [open])

  const startCreate = () => {
    setEditingId(null)
    setForm({ ...EMPTY_FORM, protocols: availableProtocols[0] ? [availableProtocols[0].id] : [] })
  }

  const startEdit = (preset: PresetResponse) => {
    setEditingId(preset.id)
    setForm(formFromPreset(preset))
  }

  const save = async () => {
    if (!form) return
    if (!form.name.trim()) {
      notifyError('Укажите название шаблона')
      return
    }
    if (form.node_ids.length === 0 || form.protocols.length === 0) {
      notifyError('Выберите хотя бы один узел и один протокол')
      return
    }
    const count = Number.parseInt(form.config_count, 10)
    if (!Number.isFinite(count) || count < 1 || count > 20) {
      notifyError('Число конфигов — от 1 до 20')
      return
    }
    const days = form.access_days.trim() === '' ? null : Number.parseInt(form.access_days, 10)
    if (days != null && (!Number.isFinite(days) || days < 1)) {
      notifyError('Срок доступа — целое число дней от 1')
      return
    }
    const gb = form.traffic_gb.trim() === '' ? null : Number.parseFloat(form.traffic_gb)
    if (gb != null && (!Number.isFinite(gb) || gb < 0)) {
      notifyError('Лимит трафика — число в гигабайтах')
      return
    }
    const quota = form.config_quota.trim() === '' ? null : Number.parseInt(form.config_quota, 10)
    if (quota != null && (!Number.isFinite(quota) || quota < 0)) {
      notifyError('Квота имён — целое число от 0')
      return
    }

    const payload: PresetBase = {
      name: form.name.trim(),
      node_ids: [...form.node_ids].sort((a, b) => a - b),
      protocols: [...form.protocols],
      config_count: count,
      config_quota: quota,
      traffic_limit_bytes: gb != null ? Math.round(gb * GB) : null,
      access_days: days,
      is_default: form.is_default,
    }

    setSaving(true)
    try {
      if (editingId != null) await updatePreset(editingId, payload)
      else await createPreset(payload)
      success(editingId != null ? 'Шаблон обновлён' : 'Шаблон создан')
      setForm(null)
      setEditingId(null)
      await reload()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось сохранить шаблон')
    } finally {
      setSaving(false)
    }
  }

  const makeDefault = async (preset: PresetResponse) => {
    try {
      await updatePreset(preset.id, { is_default: true })
      success(`«${preset.name}» — шаблон по умолчанию`)
      await reload()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось назначить шаблон')
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setSaving(true)
    try {
      await deletePreset(deleteTarget.id)
      success(`Шаблон «${deleteTarget.name}» удалён`)
      if (editingId === deleteTarget.id) {
        setForm(null)
        setEditingId(null)
      }
      setDeleteTarget(null)
      await reload()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось удалить шаблон')
    } finally {
      setSaving(false)
    }
  }

  const toggleId = (list: number[], id: number): number[] =>
    list.includes(id) ? list.filter((item) => item !== id) : [...list, id]
  const toggleProtocol = (list: string[], id: string): string[] =>
    list.includes(id) ? list.filter((item) => item !== id) : [...list, id]

  const inner = form ? (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="preset-name">Название</Label>
        <Input
          id="preset-name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Например: Базовый 30 дней"
          className="h-9"
          autoFocus
        />
      </div>

      <div className="space-y-1.5">
        <Label>Узлы</Label>
        {assignableNodes.length === 0 ? (
          <p className="text-xs text-muted-foreground">Нет доступных узлов.</p>
        ) : (
          <div className="max-h-40 space-y-0.5 overflow-y-auto rounded-lg border p-1">
            {assignableNodes.map((node) => {
              const checked = form.node_ids.includes(node.id)
              return (
                <label
                  key={node.id}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-2.5 py-2 transition-colors',
                    checked ? 'bg-primary/5' : 'hover:bg-muted/50',
                  )}
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() =>
                      setForm({ ...form, node_ids: toggleId(form.node_ids, node.id) })
                    }
                    aria-label={node.name}
                  />
                  <span className="min-w-0 flex-1 truncate text-sm">{node.name}</span>
                </label>
              )
            })}
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        <Label>Протоколы</Label>
        <div className="flex flex-wrap gap-1.5">
          {availableProtocols.map((proto) => {
            const checked = form.protocols.includes(proto.id)
            return (
              <label
                key={proto.id}
                className={cn(
                  'flex cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm transition-colors',
                  checked
                    ? 'border-primary/40 bg-primary/5 text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() =>
                    setForm({ ...form, protocols: toggleProtocol(form.protocols, proto.id) })
                  }
                  aria-label={protocolLabel(proto.id)}
                />
                {protocolLabel(proto.id)}
              </label>
            )
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="space-y-1.5">
          <Label htmlFor="preset-count">Конфигов</Label>
          <Input
            id="preset-count"
            type="number"
            min={1}
            max={20}
            value={form.config_count}
            onChange={(e) => setForm({ ...form, config_count: e.target.value })}
            className="h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="preset-days">Срок, дн.</Label>
          <Input
            id="preset-days"
            type="number"
            min={1}
            value={form.access_days}
            onChange={(e) => setForm({ ...form, access_days: e.target.value })}
            placeholder="без срока"
            className="h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="preset-traffic">Лимит, ГБ</Label>
          <Input
            id="preset-traffic"
            type="number"
            min={0}
            step="0.5"
            value={form.traffic_gb}
            onChange={(e) => setForm({ ...form, traffic_gb: e.target.value })}
            placeholder="без лимита"
            className="h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="preset-quota">Квота имён</Label>
          <Input
            id="preset-quota"
            type="number"
            min={0}
            value={form.config_quota}
            onChange={(e) => setForm({ ...form, config_quota: e.target.value })}
            placeholder="общий"
            className="h-9"
          />
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 rounded-lg border bg-muted/20 p-3">
        <div className="space-y-0.5">
          <Label htmlFor="preset-default">Шаблон по умолчанию</Label>
          <p className="text-xs text-muted-foreground">
            По нему бот одобряет заявки в один клик; флаг снимается с остальных шаблонов.
          </p>
        </div>
        <Switch
          id="preset-default"
          checked={form.is_default}
          onCheckedChange={(checked) => setForm({ ...form, is_default: checked })}
        />
      </div>
    </div>
  ) : loading ? (
    <Spinner label="Загрузка шаблонов…" className="py-10" />
  ) : presets.length === 0 ? (
    <div className="space-y-3 py-6 text-center">
      <p className="text-sm font-medium">Ни одного шаблона</p>
      <p className="mx-auto max-w-sm text-xs text-muted-foreground">
        Без шаблона «по умолчанию» бот не может одобрить заявку одним кликом и предлагает открыть
        панель. Создайте шаблон — заявки начнут одобряться прямо из Telegram.
      </p>
      <Button type="button" size="sm" onClick={startCreate}>
        <Plus size={16} /> Создать шаблон
      </Button>
    </div>
  ) : (
    <div className="space-y-2">
      {presets.map((preset) => (
        <div key={preset.id} className="rounded-lg border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                {preset.name}
                {preset.is_default && <Badge variant="secondary">по умолчанию</Badge>}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {presetMeta(preset, nodes)}
              </p>
            </div>
            <div className="flex flex-wrap gap-1">
              {!preset.is_default && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={saving}
                  onClick={() => void makeDefault(preset)}
                >
                  По умолчанию
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={saving}
                onClick={() => startEdit(preset)}
              >
                Изменить
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="gap-1 text-destructive hover:text-destructive"
                disabled={saving}
                onClick={() => setDeleteTarget(preset)}
                title={`Удалить «${preset.name}»`}
              >
                <Trash2 size={14} />
              </Button>
            </div>
          </div>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={startCreate}>
        <Plus size={16} /> Создать шаблон
      </Button>
    </div>
  )

  return (
    <>
      <AppDialog
        open={open}
        onOpenChange={onOpenChange}
        title={form ? (editingId != null ? 'Изменение шаблона' : 'Новый шаблон') : 'Шаблоны предоставления'}
        description={
          form
            ? 'Заготовка плана: узлы, протоколы, число конфигов и срок доступа нового абонента.'
            : 'По шаблону «по умолчанию» бот одобряет заявки в один клик.'
        }
        icon={Layers}
        size="md"
        footer={
          form ? (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setForm(null)
                  setEditingId(null)
                }}
                disabled={saving}
              >
                Назад к списку
              </Button>
              <Button type="button" disabled={saving} onClick={() => void save()}>
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                {editingId != null ? 'Сохранить' : 'Создать'}
              </Button>
            </>
          ) : undefined
        }
      >
        {inner}
      </AppDialog>

      <AppDialog
        open={deleteTarget != null}
        onOpenChange={(next) => {
          if (!next) setDeleteTarget(null)
        }}
        title="Удалить шаблон?"
        description={deleteTarget ? `«${deleteTarget.name}» — действие нельзя отменить.` : undefined}
        size="sm"
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => setDeleteTarget(null)}>
              Отмена
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={saving}
              onClick={() => void confirmDelete()}
            >
              Удалить
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">
          Абоненты, созданные по этому шаблону, не изменятся — шаблон нужен только для новых
          одобрений.
        </p>
      </AppDialog>
    </>
  )
}
