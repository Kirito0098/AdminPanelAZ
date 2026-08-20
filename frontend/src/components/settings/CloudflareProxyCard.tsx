import { useCallback, useEffect, useState } from 'react'
import { Cloud, Loader2, RefreshCw } from 'lucide-react'
import {
  ApiError,
  getCloudflareProxySettings,
  refreshCloudflareProxy,
  updateCloudflareProxySettings,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { formatDateTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { CloudflareProxySettings } from '@/types'

const INTERVAL_MIN = 1
const INTERVAL_MAX = 90

function clampIntervalDays(value: number): number {
  return Math.min(INTERVAL_MAX, Math.max(INTERVAL_MIN, value))
}

function shortHash(value: string | null | undefined): string | null {
  if (!value) return null
  if (value.length <= 12) return value
  return `${value.slice(0, 8)}…${value.slice(-4)}`
}

export default function CloudflareProxyCard() {
  const { success, error: notifyError } = useNotifications()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [settings, setSettings] = useState<CloudflareProxySettings | null>(null)
  const [intervalDraft, setIntervalDraft] = useState('7')

  const hydrate = useCallback((data: CloudflareProxySettings) => {
    setSettings(data)
    setIntervalDraft(String(data.interval_days))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getCloudflareProxySettings()
      hydrate(data)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Не удалось загрузить настройки Cloudflare'
      setLoadError(message)
    } finally {
      setLoading(false)
    }
  }, [hydrate])

  useEffect(() => {
    void load()
  }, [load])

  async function patchSettings(
    patch: Partial<Pick<CloudflareProxySettings, 'enabled' | 'auto_update' | 'interval_days'>>,
    opts?: { silent?: boolean },
  ) {
    if (!settings) return
    setSaving(true)
    try {
      const updated = await updateCloudflareProxySettings(patch)
      hydrate(updated)
      if (!opts?.silent) {
        success('Настройки Cloudflare сохранены')
      }
    } catch (err) {
      hydrate(settings)
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить настройки Cloudflare')
    } finally {
      setSaving(false)
    }
  }

  async function handleEnabledChange(checked: boolean) {
    if (!settings || saving || refreshing) return
    setSettings({ ...settings, enabled: checked })
    await patchSettings({ enabled: checked }, { silent: true })
  }

  async function handleAutoUpdateChange(checked: boolean) {
    if (!settings || saving || refreshing) return
    setSettings({ ...settings, auto_update: checked })
    await patchSettings({ auto_update: checked }, { silent: true })
  }

  async function commitIntervalDraft() {
    if (!settings || saving || refreshing) return
    const parsed = Number.parseInt(intervalDraft, 10)
    if (!Number.isFinite(parsed)) {
      setIntervalDraft(String(settings.interval_days))
      return
    }
    const next = clampIntervalDays(parsed)
    setIntervalDraft(String(next))
    if (next === settings.interval_days) return
    setSettings({ ...settings, interval_days: next })
    await patchSettings({ interval_days: next }, { silent: true })
  }

  async function handleRefreshNow() {
    if (!settings?.enabled || saving || refreshing) return
    setRefreshing(true)
    try {
      const resp = await refreshCloudflareProxy(false)
      hydrate(resp.state)
      if (resp.success) {
        success(resp.message || 'Списки IP Cloudflare обновлены')
      } else {
        notifyError(resp.error || resp.message || 'Не удалось обновить списки IP Cloudflare')
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось обновить списки IP Cloudflare')
    } finally {
      setRefreshing(false)
    }
  }

  const busy = loading || saving || refreshing

  if (loading) {
    return (
      <Card className="shadow-sm">
        <CardContent className="flex items-center gap-3 py-8 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          Загрузка Cloudflare…
        </CardContent>
      </Card>
    )
  }

  if (loadError) {
    return (
      <Card className="shadow-sm">
        <CardContent className="space-y-3 py-6">
          <SettingsAlert variant="danger" title="Cloudflare proxy-mode недоступен">
            {loadError}
          </SettingsAlert>
          <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
            Повторить
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (!settings) return null

  const hashLabel = shortHash(settings.last_hash)

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Cloud size={18} className="text-primary" />
            Cloudflare proxy-mode
          </CardTitle>
          <Badge variant={settings.enabled ? 'success' : 'secondary'}>
            {settings.enabled ? 'включён' : 'выключен'}
          </Badge>
        </div>
        <CardDescription className="mt-1.5">
          Для Telegram webhook за Cloudflare в режиме Proxied (orange-cloud). Nginx подставляет реальный IP
          клиента из списков Cloudflare. Без Cloudflare можно выключить.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div
          className={cn(
            'flex items-start justify-between gap-4 rounded-xl border bg-muted/15 px-4 py-3',
            settings.enabled && 'border-primary/20 bg-primary/5',
          )}
        >
          <div className="min-w-0">
            <p className="text-sm font-medium">Cloudflare proxy-mode</p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Включите, если домен панели за Cloudflare с оранжевым облаком. Без Cloudflare оставьте выключенным.
            </p>
          </div>
          <Switch
            checked={settings.enabled}
            disabled={busy}
            onCheckedChange={(checked) => void handleEnabledChange(checked)}
            aria-label="Cloudflare proxy-mode"
          />
        </div>

        <div className="flex items-start justify-between gap-4 rounded-xl border bg-muted/15 px-4 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium">Автообновление списков IP Cloudflare</p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Планировщик панели периодически скачивает актуальные CIDR Cloudflare и обновляет nginx snippet.
            </p>
          </div>
          <Switch
            checked={settings.auto_update}
            disabled={busy || !settings.enabled}
            onCheckedChange={(checked) => void handleAutoUpdateChange(checked)}
            aria-label="Автообновление списков IP Cloudflare"
          />
        </div>

        <div className="grid gap-4 sm:max-w-xs">
          <div className="space-y-2">
            <Label htmlFor="cloudflare-interval-days">Интервал автообновления (дней)</Label>
            <Input
              id="cloudflare-interval-days"
              type="number"
              min={INTERVAL_MIN}
              max={INTERVAL_MAX}
              value={intervalDraft}
              disabled={busy || !settings.enabled || !settings.auto_update}
              onChange={(event) => setIntervalDraft(event.target.value)}
              onBlur={() => void commitIntervalDraft()}
            />
            <p className="text-xs text-muted-foreground">От {INTERVAL_MIN} до {INTERVAL_MAX} дней</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            className="gap-2"
            disabled={!settings.enabled || busy}
            onClick={() => void handleRefreshNow()}
          >
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw size={16} />}
            Обновить сейчас
          </Button>
        </div>

        <div className="space-y-2 rounded-xl border bg-card/50 px-4 py-3 text-sm">
          <p className="text-muted-foreground">
            Последнее успешное обновление:{' '}
            <span className="text-foreground">{formatDateTime(settings.last_success_at)}</span>
            {hashLabel ? (
              <>
                {' '}
                · hash <code className="font-mono text-xs">{hashLabel}</code>
              </>
            ) : null}
          </p>
          {settings.last_error ? (
            <p className="text-destructive">
              Последняя ошибка: <span className="font-medium">{settings.last_error}</span>
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">Ошибок обновления нет</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
