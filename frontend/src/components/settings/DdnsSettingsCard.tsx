import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { Globe2, Loader2, RefreshCw, Save } from 'lucide-react'
import {
  ApiError,
  getDdnsSettings,
  runDdnsUpdate,
  updateDdnsSettings,
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
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import type { DdnsProvider, DdnsSettings } from '@/types'

type Props = {
  /** Prefill publish wizard domain when empty and DDNS FQDN is known. */
  onSuggestDomain?: (domain: string) => void
}

function applySettingsToForm(data: DdnsSettings) {
  return {
    provider: (data.provider || 'none') as DdnsProvider,
    subdomain: data.subdomain || '',
    token: data.token_configured ? data.token_masked || '****' : '',
    hostname: data.hostname || data.domain || '',
    username: data.username || '',
    password: data.password_configured ? data.password_masked || '****' : '',
    enableTimer: data.timer_enabled,
  }
}

export default function DdnsSettingsCard({ onSuggestDomain }: Props) {
  const { success, error: notifyError } = useNotifications()
  const onSuggestDomainRef = useRef(onSuggestDomain)
  onSuggestDomainRef.current = onSuggestDomain
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [settings, setSettings] = useState<DdnsSettings | null>(null)
  const [provider, setProvider] = useState<DdnsProvider>('none')
  const [subdomain, setSubdomain] = useState('')
  const [token, setToken] = useState('')
  const [hostname, setHostname] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [enableTimer, setEnableTimer] = useState(true)

  const hydrate = useCallback((data: DdnsSettings) => {
    setSettings(data)
    const form = applySettingsToForm(data)
    setProvider(form.provider)
    setSubdomain(form.subdomain)
    setToken(form.token)
    setHostname(form.hostname)
    setUsername(form.username)
    setPassword(form.password)
    setEnableTimer(form.enableTimer)
    if (data.configured && data.domain) {
      onSuggestDomainRef.current?.(data.domain)
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getDdnsSettings()
      hydrate(data)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Не удалось загрузить DDNS'
      setLoadError(message)
    } finally {
      setLoading(false)
    }
  }, [hydrate])

  useEffect(() => {
    void load()
  }, [load])

  async function handleSave(event: FormEvent) {
    event.preventDefault()
    if (provider === 'duckdns') {
      const sub = subdomain.trim().replace(/\.duckdns\.org$/i, '')
      if (!sub) {
        notifyError('Укажите поддомен DuckDNS')
        return
      }
      if (!token.trim()) {
        notifyError('Укажите DuckDNS token')
        return
      }
    }
    if (provider === 'noip') {
      if (!hostname.trim()) {
        notifyError('Укажите hostname No-IP')
        return
      }
      if (!username.trim()) {
        notifyError('Укажите логин No-IP')
        return
      }
      if (!password.trim()) {
        notifyError('Укажите пароль No-IP')
        return
      }
    }

    setSaving(true)
    try {
      const resp = await updateDdnsSettings({
        provider,
        subdomain: provider === 'duckdns' ? subdomain.trim() : null,
        token: provider === 'duckdns' ? token : null,
        hostname: provider === 'noip' ? hostname.trim() : null,
        username: provider === 'noip' ? username.trim() : null,
        password: provider === 'noip' ? password : null,
        enable_timer: provider === 'none' ? false : enableTimer,
        run_update: provider !== 'none',
      })
      hydrate(resp.settings)
      success(resp.message)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить DDNS')
    } finally {
      setSaving(false)
    }
  }

  async function handleUpdateNow() {
    setUpdating(true)
    try {
      const resp = await runDdnsUpdate()
      hydrate(resp.settings)
      success(resp.message)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось обновить IP')
    } finally {
      setUpdating(false)
    }
  }

  if (loading) {
    return (
      <Card className="overflow-hidden shadow-sm md:col-span-2">
        <CardContent className="flex items-center gap-3 py-8 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          Загрузка DDNS…
        </CardContent>
      </Card>
    )
  }

  if (loadError) {
    return (
      <Card className="overflow-hidden shadow-sm md:col-span-2">
        <CardContent className="space-y-3 py-6">
          <SettingsAlert variant="danger" title="DDNS недоступен">
            {loadError}
          </SettingsAlert>
          <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
            Повторить
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="overflow-hidden shadow-sm md:col-span-2">
      <div className="h-1 bg-gradient-to-r from-teal-500/70 to-teal-500/15" />
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Globe2 size={18} />
            Динамический DNS
          </CardTitle>
          {settings?.configured ? (
            <Badge variant="success">{settings.domain || settings.provider}</Badge>
          ) : (
            <Badge variant="secondary">не настроен</Badge>
          )}
        </div>
        <CardDescription className="mt-1.5">
          Бесплатный адрес (DuckDNS / No-IP), если нет своего домена. После сохранения укажите этот
          адрес в мастере «Адрес сайта и HTTPS».
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={(e) => void handleSave(e)}>
          <div className="space-y-2">
            <Label htmlFor="ddns-provider">Провайдер</Label>
            <Select
              value={provider}
              onValueChange={(value) => setProvider(value as DdnsProvider)}
            >
              <SelectTrigger id="ddns-provider">
                <SelectValue placeholder="Выберите провайдера" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Не использую DDNS (свой домен или IP)</SelectItem>
                <SelectItem value="duckdns">DuckDNS (*.duckdns.org)</SelectItem>
                <SelectItem value="noip">No-IP (*.ddns.net и др.)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {provider === 'duckdns' && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="ddns-subdomain">Поддомен (без .duckdns.org)</Label>
                <Input
                  id="ddns-subdomain"
                  value={subdomain}
                  onChange={(e) => setSubdomain(e.target.value)}
                  placeholder="myvpn"
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ddns-token">Token</Label>
                <Input
                  id="ddns-token"
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder={settings?.token_configured ? '••••••••' : 'token с duckdns.org'}
                  autoComplete="off"
                />
              </div>
            </div>
          )}

          {provider === 'noip' && (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="ddns-hostname">Hostname</Label>
                <Input
                  id="ddns-hostname"
                  value={hostname}
                  onChange={(e) => setHostname(e.target.value)}
                  placeholder="myvpn.ddns.net"
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ddns-username">Логин</Label>
                <Input
                  id="ddns-username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ddns-password">Пароль</Label>
                <Input
                  id="ddns-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={settings?.password_configured ? '••••••••' : ''}
                  autoComplete="off"
                />
              </div>
            </div>
          )}

          {provider !== 'none' && (
            <div className="flex items-center justify-between gap-4 rounded-xl border bg-muted/15 px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">Автообновление IP</p>
                <p className="text-xs text-muted-foreground">
                  systemd timer каждые 5 минут
                  {settings?.timer_detail ? ` — ${settings.timer_detail}` : ''}
                </p>
              </div>
              <Switch
                checked={enableTimer}
                onCheckedChange={setEnableTimer}
                aria-label="Автообновление IP"
              />
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={saving || updating} className="gap-2">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save size={16} />}
              Сохранить
            </Button>
            {settings?.configured && provider !== 'none' && (
              <Button
                type="button"
                variant="outline"
                disabled={saving || updating}
                className="gap-2"
                onClick={() => void handleUpdateNow()}
              >
                {updating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw size={16} />}
                Обновить IP сейчас
              </Button>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
