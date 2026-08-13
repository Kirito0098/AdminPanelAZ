import { RefreshCw, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  applyAwg2Obfuscation,
  getAwg2Obfuscation,
  regenerateAwg2Obfuscation,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import { formatDateTime } from '@/lib/datetime'
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
  const hasProfile = Boolean(profile?.preset || preview.length > 0)

  return (
    <div className="space-y-4">
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

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="text-base">Применить preset</CardTitle>
            <CardDescription>
              После apply нужен re-import конфигов на устройствах ·{' '}
              <code className="text-[11px]">awg-obfuscation --apply</code>
            </CardDescription>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {profile?.preset && <Badge variant="secondary">{profile.preset}</Badge>}
              {profile?.template && <Badge variant="outline">{profile.template}</Badge>}
              {profile?.fp && <Badge variant="outline">{profile.fp}</Badge>}
              {profile?.mtu != null && profile.mtu !== '' && (
                <Badge variant="outline" className="font-mono">
                  MTU {profile.mtu}
                </Badge>
              )}
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 gap-1.5 self-start"
            disabled={busy || disabled}
            onClick={() => void load()}
          >
            <RefreshCw className="h-4 w-4" />
            Обновить
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
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
            <div className="space-y-1.5 sm:col-span-2 lg:col-span-2">
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

          <div className="flex flex-wrap items-center justify-end gap-2 border-t pt-4">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy || disabled}
              onClick={() => void onRegenerate()}
            >
              <Sparkles className="mr-1.5 h-4 w-4" />
              Regenerate
            </Button>
            <Button type="button" size="sm" disabled={disabled || busy} onClick={() => void onApply()}>
              Применить
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Текущий профиль</CardTitle>
          <CardDescription>Активные параметры на узле после последнего apply / regenerate</CardDescription>
        </CardHeader>
        <CardContent>
          {!hasProfile ? (
            <p className="text-sm text-muted-foreground">Профиль ещё не сгенерирован на узле.</p>
          ) : (
            <div className="space-y-3">
              <dl className="grid gap-x-6 gap-y-2 rounded-xl border bg-muted/15 px-4 py-3 text-sm sm:grid-cols-3">
                <div className="min-w-0">
                  <dt className="text-xs text-muted-foreground">Host</dt>
                  <dd className="mt-0.5 truncate font-mono text-xs font-medium" title={profile?.host || undefined}>
                    {profile?.host || '—'}
                  </dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-xs text-muted-foreground">MTU</dt>
                  <dd className="mt-0.5 font-mono text-xs font-medium">{profile?.mtu ?? '—'}</dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-xs text-muted-foreground">Generated</dt>
                  <dd
                    className="mt-0.5 truncate font-mono text-xs font-medium"
                    title={profile?.generated || undefined}
                  >
                    {profile?.generated ? formatDateTime(profile.generated) : '—'}
                  </dd>
                </div>
              </dl>

              {preview.length > 0 && (
                <div className="rounded-xl border bg-muted/10">
                  <div className="flex items-center justify-between border-b border-border/60 px-4 py-2">
                    <p className="text-xs font-medium text-muted-foreground">
                      Параметры обфускации
                      <span className="ml-1.5 tabular-nums text-muted-foreground/80">· {preview.length}</span>
                    </p>
                    <span className="text-[10px] text-muted-foreground">без I-пакетов</span>
                  </div>
                  <ul className="grid gap-px sm:grid-cols-2 lg:grid-cols-3">
                    {preview.map(([key, value]) => (
                      <li
                        key={key}
                        className="flex min-w-0 items-baseline justify-between gap-3 bg-card/40 px-4 py-2"
                        title={`${key}=${value}`}
                      >
                        <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{key}</span>
                        <span className="truncate font-mono text-[11px] tabular-nums">{value}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
