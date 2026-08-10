import { RefreshCw, Shield, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  applyAwg2Obfuscation,
  getAwg2Obfuscation,
  regenerateAwg2Obfuscation,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import Spinner from '@/components/ui/Spinner'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { Awg2HealthResponse, Awg2ObfuscationResponse } from '@/types'
import { AWG2_PRESETS, AWG2_TEMPLATES } from './utils'

const FPS = [
  { value: 'chrome', label: 'chrome' },
  { value: 'firefox', label: 'firefox' },
  { value: 'safari', label: 'safari' },
] as const

interface ObfuscationTabProps {
  health: Awg2HealthResponse | null
}

function paramPreview(params?: Record<string, string>) {
  if (!params) return []
  return Object.entries(params)
    .filter(([key]) => !/^I\d+$/i.test(key))
    .slice(0, 12)
}

export default function ObfuscationTab({ health }: ObfuscationTabProps) {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const disabled = !health?.installed

  const [profile, setProfile] = useState<Awg2ObfuscationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [reimportAlert, setReimportAlert] = useState(false)
  const [haErrors, setHaErrors] = useState<Array<{ node_name?: string | null; error?: string | null }>>([])

  const [preset, setPreset] = useState<string>('medium')
  const [template, setTemplate] = useState<string>('web')
  const [fp, setFp] = useState<string>('chrome')
  const [mtu, setMtu] = useState('')
  const [host, setHost] = useState('')

  const applyProfileToForm = useCallback((data: Awg2ObfuscationResponse) => {
    if (data.preset) setPreset(data.preset)
    if (data.template) setTemplate(data.template)
    if (data.fp) setFp(data.fp)
    if (data.mtu != null && data.mtu !== '') setMtu(String(data.mtu))
    if (typeof data.host === 'string') setHost(data.host)
  }, [])

  const load = useCallback(async () => {
    if (!health?.installed) {
      setProfile(null)
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await getAwg2Obfuscation()
      setProfile(data)
      applyProfileToForm(data)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось загрузить профиль обфускации')
    } finally {
      setLoading(false)
    }
  }, [applyProfileToForm, health?.installed, notifyError])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  function handleMutateResult(data: Awg2ObfuscationResponse, message: string) {
    setProfile(data)
    applyProfileToForm(data)
    setReimportAlert(Boolean(data.reimport_required))
    setHaErrors(data.ha?.errors ?? [])
    success(message)
  }

  async function onRegenerate() {
    setBusy(true)
    try {
      const data = await regenerateAwg2Obfuscation()
      handleMutateResult(data, 'Профиль обфускации перегенерирован')
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка regenerate')
    } finally {
      setBusy(false)
    }
  }

  async function onApply() {
    setBusy(true)
    try {
      const mtuValue = mtu.trim() ? Number(mtu) : undefined
      if (mtu.trim() && !Number.isFinite(mtuValue)) {
        notifyError('MTU должен быть числом')
        return
      }
      const data = await applyAwg2Obfuscation({
        preset,
        template,
        mtu: mtuValue,
        host: host.trim() || null,
        fp: fp || null,
      })
      handleMutateResult(data, 'Профиль обфускации применён')
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка apply')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner label="Загрузка обфускации..." />
      </div>
    )
  }

  const preview = paramPreview(profile?.params)

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Shield className="h-4 w-4 text-primary" />
            Обфускация AmneziaWG 2.0
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Пресет и шаблон мимикрии на активном узле. После apply клиентам нужен re-import конфигов.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {profile?.preset && <Badge variant="secondary">Сейчас: {profile.preset}</Badge>}
          {profile?.template && <Badge variant="outline">{profile.template}</Badge>}
          <Button variant="secondary" size="sm" disabled={busy || disabled} onClick={() => void load()}>
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Обновить
          </Button>
        </div>
      </div>

      {reimportAlert && (
        <SettingsAlert variant="warning" title="Требуется re-import">
          Параметры обфускации изменились. Переимпортируйте клиентские конфиги AmneziaWG 2.0 на устройствах.
        </SettingsAlert>
      )}

      {haErrors.length > 0 && (
        <SettingsAlert variant="warning" title="HA sync: предупреждения">
          <ul className="list-disc space-y-1 pl-4">
            {haErrors.map((item, index) => (
              <li key={`${item.node_name ?? 'node'}-${index}`}>
                {item.node_name ? `${item.node_name}: ` : ''}
                {item.error || 'ошибка синхронизации'}
              </li>
            ))}
          </ul>
        </SettingsAlert>
      )}

      <div className="rounded-lg border bg-card/40 p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium">Текущий профиль</h3>
          <Button size="sm" variant="secondary" disabled={busy || disabled} onClick={() => void onRegenerate()}>
            <Sparkles className="mr-1.5 h-4 w-4" />
            Regenerate
          </Button>
        </div>
        {profile?.preset || preview.length > 0 ? (
          <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">Preset</dt>
              <dd className="font-mono text-xs">{profile?.preset || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Template</dt>
              <dd className="font-mono text-xs">{profile?.template || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">FP</dt>
              <dd className="font-mono text-xs">{profile?.fp || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">MTU</dt>
              <dd className="font-mono text-xs">{profile?.mtu ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Host</dt>
              <dd className="font-mono text-xs">{profile?.host || '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Generated</dt>
              <dd className="font-mono text-xs">{profile?.generated || '—'}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">Профиль ещё не сгенерирован на узле.</p>
        )}
        {preview.length > 0 && (
          <div className="mt-4 rounded-md border bg-muted/10 p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">Параметры (без I-пакетов)</p>
            <ul className="grid gap-1 font-mono text-[11px] sm:grid-cols-2 lg:grid-cols-3">
              {preview.map(([key, value]) => (
                <li key={key} className="truncate" title={`${key}=${value}`}>
                  {key}={value}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="rounded-lg border p-4">
        <h3 className="mb-1 text-sm font-medium">Применить preset / template</h3>
        <p className="mb-4 text-xs text-muted-foreground">
          Вызов <code className="text-[11px]">awg-obfuscation --apply</code> и затем{' '}
          <code className="text-[11px]">awg-client regen-all</code>.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="awg2-obf-preset">Preset</Label>
            <Select value={preset} onValueChange={setPreset} disabled={disabled || busy}>
              <SelectTrigger id="awg2-obf-preset">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AWG2_PRESETS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="awg2-obf-template">Template</Label>
            <Select value={template} onValueChange={setTemplate} disabled={disabled || busy}>
              <SelectTrigger id="awg2-obf-template">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AWG2_TEMPLATES.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="awg2-obf-fp">Fingerprint</Label>
            <Select value={fp} onValueChange={setFp} disabled={disabled || busy}>
              <SelectTrigger id="awg2-obf-fp">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FPS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="awg2-obf-mtu">MTU (опционально)</Label>
            <Input
              id="awg2-obf-mtu"
              type="number"
              min={576}
              max={1500}
              placeholder="1280"
              value={mtu}
              disabled={disabled || busy}
              onChange={(e) => setMtu(e.target.value)}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="awg2-obf-host">Host (опционально)</Label>
            <Input
              id="awg2-obf-host"
              placeholder="yandex.ru"
              value={host}
              disabled={disabled || busy}
              onChange={(e) => setHost(e.target.value)}
            />
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <Button disabled={disabled || busy} onClick={() => void onApply()}>
            Применить
          </Button>
        </div>
      </div>
    </div>
  )
}
