import { useEffect, useState } from 'react'
import { ExternalLink, Globe, Terminal } from 'lucide-react'
import { ApiError, getVpnNetworkSettings } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useNotifications } from '@/context/NotificationContext'
import type { VpnNetworkSettings } from '@/types'

const MODE_LABELS: Record<string, string> = {
  reverse_proxy: 'Nginx / прокси',
  direct_http: 'Прямой HTTP',
  local_http: 'Localhost HTTP',
}

function modeBadgeVariant(modeKey: string): 'default' | 'secondary' | 'outline' {
  if (modeKey === 'reverse_proxy') return 'default'
  if (modeKey === 'direct_http') return 'secondary'
  return 'outline'
}

export default function VpnNetworkTab() {
  const { error: notifyError } = useNotifications()
  const [settings, setSettings] = useState<VpnNetworkSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setLoadError(null)
    getVpnNetworkSettings()
      .then(setSettings)
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : 'Ошибка загрузки'
        setLoadError(message)
        notifyError(message)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading && !settings) {
    return <Spinner label="Загрузка настроек публикации..." className="py-12" />
  }

  if (loadError && !settings) {
    return (
      <SettingsAlert variant="danger" title="Не удалось загрузить настройки">
        {loadError}
      </SettingsAlert>
    )
  }

  if (!settings) {
    return null
  }

  const modeLabel = MODE_LABELS[settings.mode_key] ?? settings.mode_title

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Сеть и публикация</p>
        <h2 className="mt-1 text-lg font-semibold">Порт, HTTPS и Nginx</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Как устроен доступ к панели: прямой HTTP на порту uvicorn или TLS на Nginx (reverse proxy).
        </p>
      </header>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={modeBadgeVariant(settings.mode_key)}>{modeLabel}</Badge>
            <CardTitle className="text-base">{settings.mode_title}</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="grid gap-6 lg:grid-cols-[1fr_minmax(220px,280px)]">
          <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            {settings.bullet_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          <aside className="space-y-4 rounded-lg border bg-muted/30 p-4 text-sm">
            <div>
              <p className="text-xs font-medium text-muted-foreground">Процесс панели (listen)</p>
              <code className="mt-1 block break-all rounded bg-muted px-2 py-1 text-xs">
                {settings.internal_url}
              </code>
            </div>
            {settings.primary_urls.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Вход в панель</p>
                {settings.primary_urls.map((row) => (
                  <a
                    key={row.url}
                    href={row.url}
                    className="flex flex-col gap-0.5 rounded-md border bg-background px-3 py-2 transition-colors hover:bg-muted/50"
                    title={row.label}
                  >
                    <span className="text-xs text-muted-foreground">{row.label}</span>
                    <span className="flex items-center gap-1 break-all font-mono text-xs text-primary">
                      {row.url}
                      <ExternalLink size={12} className="shrink-0" />
                    </span>
                  </a>
                ))}
              </div>
            )}
          </aside>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Globe size={18} />
            Параметры из .env
          </CardTitle>
          <CardDescription>
            Справочно: прямой HTTP, localhost-only или схема с Nginx — отражается этими переменными.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="divide-y rounded-lg border">
            {settings.env_rows.map((row) => (
              <div
                key={row.label}
                className="grid gap-1 px-4 py-3 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] sm:gap-4"
              >
                <dt className="text-sm text-muted-foreground">{row.label}</dt>
                <dd className="text-sm">
                  {row.mono ? (
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{row.value}</code>
                  ) : (
                    row.value
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Terminal size={18} />
            Смена режима и порта
          </CardTitle>
          <CardDescription>
            Текущий порт uvicorn: <strong>{settings.backend_port}</strong>. При Nginx это внутренний upstream, а не
            443.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            Для смены режима HTTPS/Nginx, домена или порта выполните на сервере:
          </p>
          <code className="block rounded-lg border bg-muted/50 px-3 py-2 font-mono text-xs">
            sudo ./{settings.nginx_setup_hint}
          </code>
          <p>
            Первичная установка и публикация также описаны в <code>README.md</code> (разделы «Nginx + Let&apos;s Encrypt» и
            «scripts/nginx-setup.sh»).
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
