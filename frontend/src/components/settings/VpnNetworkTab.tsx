import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, Globe, Rocket, Terminal } from 'lucide-react'
import { ApiError, getVpnNetworkSettings, publishVpnNetwork } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import type { VpnNetworkPublishMode, VpnNetworkSettings } from '@/types'

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
  const { success, error: notifyError } = useNotifications()
  const { inline, trackBackgroundTask, backgroundTaskPolling } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [settings, setSettings] = useState<VpnNetworkSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedMode, setSelectedMode] = useState<string>('nginx_le')
  const [backendPort, setBackendPort] = useState('8000')
  const [domain, setDomain] = useState('')
  const [email, setEmail] = useState('')
  const [httpsPublicPort, setHttpsPublicPort] = useState('443')
  const [httpAcmePort, setHttpAcmePort] = useState('80')
  const [publishing, setPublishing] = useState(false)

  const loadSettings = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getVpnNetworkSettings()
      setSettings(data)
      setBackendPort(data.backend_port || '8000')
      const domainRow = data.env_rows.find((r) => r.label.includes('DOMAIN'))
      if (domainRow && domainRow.value !== '—') {
        setDomain(domainRow.value)
      }
      if (data.publish_modes?.length) {
        setSelectedMode(data.publish_modes[0].key)
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Ошибка загрузки'
      setLoadError(message)
      notifyError(message)
    } finally {
      setLoading(false)
    }
  }, [notifyError])

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  const selectedModeInfo: VpnNetworkPublishMode | undefined = settings?.publish_modes?.find(
    (m) => m.key === selectedMode,
  )

  const handlePublish = () => {
    if (!selectedModeInfo) return

    const port = Number(backendPort)
    const httpsPort = Number(httpsPublicPort)
    const httpPort = Number(httpAcmePort)
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      notifyError('Некорректный BACKEND_PORT')
      return
    }
    if (selectedModeInfo.requires_domain && !domain.trim()) {
      notifyError('Укажите домен')
      return
    }

    const isDirect = selectedMode === 'http_direct'
    confirm({
      title: 'Применить публикацию панели?',
      description: `Режим: ${selectedModeInfo.title}. Панель может быть недоступна несколько минут.`,
      alert: {
        variant: isDirect ? 'danger' : 'warning',
        title: isDirect ? 'Прямой HTTP' : 'Изменение публикации',
        children: isDirect
          ? (selectedModeInfo.warning ||
            'Не используйте прямой HTTP в интернете. Включите блок на порту панели в разделе «Безопасность».')
          : 'Будет запущен scripts/nginx-setup.sh на controller. Убедитесь, что DNS и firewall настроены.',
      },
      confirmLabel: 'Запустить публикацию',
      destructive: isDirect,
      onConfirm: async () => {
        setPublishing(true)
        try {
          const resp = await publishVpnNetwork({
            mode: selectedMode as 'http_direct' | 'nginx_le' | 'nginx_selfsigned',
            backend_port: port,
            domain: domain.trim() || null,
            email: email.trim() || null,
            https_public_port: httpsPort,
            http_acme_port: httpPort,
          })
          trackBackgroundTask(resp.task_id, {
            onComplete: () => {
              success(resp.message || 'Публикация завершена')
              void loadSettings()
            },
            onError: (task, message) => {
              notifyError(task?.error || task?.message || message)
            },
          })
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка запуска публикации')
        } finally {
          setPublishing(false)
        }
      },
    })
  }

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
  const showNginxPorts = selectedMode !== 'http_direct'

  return (
    <div className="space-y-6">
      <InlineProgressBar active={inline.active || backgroundTaskPolling || publishing} label={inline.label} />
      <ConfirmDialogHost {...dialogProps} />

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
            <Rocket size={18} />
            Мастер публикации
          </CardTitle>
          <CardDescription>
            Запускает <code>scripts/nginx-setup.sh</code> на controller в фоне. Операция только на этом сервере.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-3">
            {(settings.publish_modes || []).map((mode) => (
              <button
                key={mode.key}
                type="button"
                onClick={() => setSelectedMode(mode.key)}
                className={`rounded-lg border p-4 text-left transition-colors ${
                  selectedMode === mode.key
                    ? 'border-primary bg-primary/5'
                    : 'hover:bg-muted/50'
                }`}
              >
                <p className="text-sm font-medium">{mode.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{mode.description}</p>
              </button>
            ))}
          </div>

          {selectedModeInfo?.warning && (
            <SettingsAlert variant="warning" title="Внимание">
              {selectedModeInfo.warning}
            </SettingsAlert>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="vpn-backend-port">BACKEND_PORT (uvicorn)</Label>
              <Input
                id="vpn-backend-port"
                type="number"
                min={1}
                max={65535}
                value={backendPort}
                onChange={(e) => setBackendPort(e.target.value)}
              />
            </div>
            {selectedModeInfo?.requires_domain && (
              <div className="space-y-2">
                <Label htmlFor="vpn-domain">DOMAIN</Label>
                <Input
                  id="vpn-domain"
                  value={domain}
                  onChange={(e) => setDomain(e.target.value)}
                  placeholder="panel.example.com"
                />
              </div>
            )}
            {selectedMode === 'nginx_le' && (
              <div className="space-y-2">
                <Label htmlFor="vpn-email">EMAIL (Let&apos;s Encrypt)</Label>
                <Input
                  id="vpn-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@example.com"
                />
              </div>
            )}
            {showNginxPorts && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="vpn-https-port">HTTPS_PUBLIC_PORT</Label>
                  <Input
                    id="vpn-https-port"
                    type="number"
                    min={1}
                    max={65535}
                    value={httpsPublicPort}
                    onChange={(e) => setHttpsPublicPort(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="vpn-http-port">HTTP_ACME_PORT</Label>
                  <Input
                    id="vpn-http-port"
                    type="number"
                    min={1}
                    max={65535}
                    value={httpAcmePort}
                    onChange={(e) => setHttpAcmePort(e.target.value)}
                  />
                </div>
              </>
            )}
          </div>

          <Button onClick={handlePublish} disabled={publishing || backgroundTaskPolling}>
            {publishing ? 'Запуск...' : 'Применить публикацию'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Terminal size={18} />
            Ручная настройка
          </CardTitle>
          <CardDescription>
            Альтернатива мастеру — выполните на сервере вручную.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <code className="block rounded-lg border bg-muted/50 px-3 py-2 font-mono text-xs">
            sudo ./{settings.nginx_setup_hint}
          </code>
          <p>
            Первичная установка описана в <code>README.md</code> (разделы «Nginx + Let&apos;s Encrypt» и
            «scripts/nginx-setup.sh»).
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
