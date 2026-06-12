import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Play, RefreshCw, Save, Settings2 } from 'lucide-react'
import {
  ApiError,
  applyRouting,
  getAntizapretSettings,
  updateAntizapretSettings,
} from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import type { AntizapretSettingField } from '@/types'

const FIELD_SECTIONS: { title: string; description?: string; keys: string[] }[] = [
  {
    title: 'Маршрутизация трафика',
    description: 'Какие сервисы направлять через AntiZapret VPN',
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
    title: 'AdBlock',
    keys: ['block_ads'],
  },
  {
    title: 'Резервные порты',
    description: 'Альтернативные порты OpenVPN и WireGuard/AmneziaWG для обхода блокировок',
    keys: ['OPENVPN_BACKUP_TCP', 'OPENVPN_BACKUP_UDP', 'WIREGUARD_BACKUP'],
  },
  {
    title: 'Cloudflare WARP',
    keys: ['ANTIZAPRET_WARP', 'VPN_WARP'],
  },
  {
    title: 'Безопасность сервера',
    keys: [
      'ssh_protection',
      'attack_protection',
      'scan_protection',
      'torrent_guard',
      'restrict_forward',
    ],
  },
  {
    title: 'Списки и хосты',
    keys: ['clear_hosts', 'openvpn_host', 'wireguard_host'],
  },
]

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
    sections.push({ title: 'Другие параметры', keys: [], fields: rest })
  }
  return sections
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

  const dirtyKeys = useMemo(
    () => schema.filter((field) => draft[field.key] !== saved[field.key]).map((field) => field.key),
    [schema, draft, saved],
  )
  const dirty = dirtyKeys.length > 0

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

  return (
    <div className="space-y-4">
      <InlineProgressBar active={saving} label="Сохранение настроек..." />
      <InlineProgressBar active={applying} label="Применение doall.sh..." />

      <StatusPanel title="Конфиг AntiZapret" icon={Settings2}>
        <p className="mb-4 text-sm text-muted-foreground">
          Параметры файла <span className="font-mono text-xs">setup</span> на активном узле. После
          сохранения выполните «Применить (doall.sh)», чтобы изменения вступили в силу.
        </p>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          {nodeName && <Badge variant="outline">Узел: {nodeName}</Badge>}
          <Badge variant="secondary">Параметров: {schema.length}</Badge>
          <Badge variant="default">Флаги вкл.: {enabledFlags}</Badge>
          {dirty && <Badge variant="outline">Несохранённых: {dirtyKeys.length}</Badge>}
          {needsApply && !dirty && (
            <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-300">
              Требуется doall.sh
            </Badge>
          )}
        </div>

        {needsApply && !dirty && (
          <SettingsAlert variant="warning" title="Требуется применение" className="mb-4">
            Настройки сохранены на узле, но ещё не активированы. Нажмите «Применить (doall.sh)».
          </SettingsAlert>
        )}

        <div className="mb-6 flex flex-wrap gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={() => void load()} disabled={saving || applying}>
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Обновить
          </Button>
          <Button type="button" size="sm" onClick={() => void save()} disabled={!dirty || saving || applying}>
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
            Применить (doall.sh)
          </Button>
        </div>

        <div className="space-y-6">
          {sections.map((section) => (
            <div key={section.title} className="space-y-3">
              <div>
                <h3 className="text-sm font-semibold">{section.title}</h3>
                {section.description && (
                  <p className="text-xs text-muted-foreground">{section.description}</p>
                )}
                {section.title === 'Cloudflare WARP' && (
                  <p className="mt-1 text-xs">
                    <Link to="/warper" className="font-medium text-primary underline-offset-4 hover:underline">
                      Управление AZ-WARP →
                    </Link>
                  </p>
                )}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {section.fields.map((field) => (
                  <div key={field.key} className="rounded-lg border p-3">
                    {field.type === 'flag' ? (
                      <>
                        <div className="mb-2 flex items-start justify-between gap-2">
                          <div>
                            <div className="font-medium text-sm">{field.title || field.key}</div>
                            <div className="text-xs text-muted-foreground font-mono">
                              {field.param_label || field.env}
                            </div>
                          </div>
                          <Badge variant={isFlagOn(draft[field.key]) ? 'default' : 'secondary'}>
                            {isFlagOn(draft[field.key]) ? 'Вкл.' : 'Выкл.'}
                          </Badge>
                        </div>
                        {field.description && (
                          <p className="mb-3 text-sm text-muted-foreground">{field.description}</p>
                        )}
                        <div className="flex gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant={isFlagOn(draft[field.key]) ? 'default' : 'secondary'}
                            disabled={saving || applying}
                            onClick={() => setDraft((prev) => ({ ...prev, [field.key]: 'y' }))}
                          >
                            Включить
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant={!isFlagOn(draft[field.key]) ? 'destructive' : 'secondary'}
                            disabled={saving || applying}
                            onClick={() => setDraft((prev) => ({ ...prev, [field.key]: 'n' }))}
                          >
                            Выключить
                          </Button>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="mb-2">
                          <div className="font-medium text-sm">{field.title || field.key}</div>
                          <div className="text-xs text-muted-foreground font-mono">
                            {field.param_label || field.env}
                          </div>
                        </div>
                        <Input
                          value={draft[field.key] ?? ''}
                          disabled={saving || applying}
                          placeholder={field.env}
                          onChange={(e) =>
                            setDraft((prev) => ({ ...prev, [field.key]: e.target.value }))
                          }
                        />
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </StatusPanel>

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
