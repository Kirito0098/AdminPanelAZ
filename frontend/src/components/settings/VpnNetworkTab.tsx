import { useCallback, useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  ExternalLink,
  Globe,
  Lock,
  Rocket,
  Server,
  Shield,
  Terminal,
  Wifi,
} from 'lucide-react'
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
import { cn } from '@/lib/utils'
import type { VpnNetworkPublishMode, VpnNetworkPublishModeKey, VpnNetworkSettings } from '@/types'

const MODE_LABELS: Record<string, string> = {
  reverse_proxy: 'Через Nginx с HTTPS',
  direct_https: 'HTTPS на uvicorn (без Nginx)',
  direct_http: 'Напрямую по HTTP',
  local_http: 'Только с этого компьютера',
}

const MODE_ICONS: Record<string, LucideIcon> = {
  reverse_proxy: Lock,
  direct_https: Shield,
  direct_http: Wifi,
  local_http: Server,
  http_direct: Wifi,
  nginx_le: Shield,
  nginx_selfsigned: Lock,
  nginx_custom: Lock,
  uvicorn_le: Shield,
  uvicorn_custom: Shield,
  uvicorn_selfsigned: Lock,
}

function envRowValue(rows: VpnNetworkSettings['env_rows'], labelPrefix: string): string {
  const row = rows.find((r) => r.label.startsWith(labelPrefix))
  return row && row.value !== '—' ? row.value : ''
}

function modeBadgeVariant(modeKey: string): 'default' | 'secondary' | 'outline' | 'success' {
  if (modeKey === 'reverse_proxy' || modeKey === 'nginx_le' || modeKey === 'direct_https') return 'success'
  if (modeKey === 'direct_http' || modeKey === 'http_direct') return 'secondary'
  return 'outline'
}

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="md:col-span-2">
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

function MetricPill({
  icon: Icon,
  label,
  value,
  tone = 'default',
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: 'default' | 'success' | 'warning' | 'muted'
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card/80 p-3 shadow-sm backdrop-blur-sm">
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
          tone === 'success' && 'bg-primary/15 text-primary',
          tone === 'warning' && 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
          tone === 'muted' && 'bg-muted text-muted-foreground',
          tone === 'default' && 'bg-muted/80 text-foreground',
        )}
      >
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-semibold">{value}</p>
      </div>
    </div>
  )
}

function publishModeIcon(key: string): LucideIcon {
  return MODE_ICONS[key] ?? Globe
}

export default function VpnNetworkTab() {
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask, backgroundTaskPolling } = useProgress()
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
  const [sslCert, setSslCert] = useState('')
  const [sslKey, setSslKey] = useState('')
  const [publishing, setPublishing] = useState(false)

  const loadSettings = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getVpnNetworkSettings()
      setSettings(data)
      setBackendPort(data.backend_port || '8000')
      const domainVal = envRowValue(data.env_rows, 'DOMAIN')
      if (domainVal) setDomain(domainVal)
      const httpsPortVal = envRowValue(data.env_rows, 'HTTPS_PUBLIC_PORT')
      if (httpsPortVal) setHttpsPublicPort(httpsPortVal)
      const certVal = envRowValue(data.env_rows, 'SSL_CERT')
      if (certVal) setSslCert(certVal)
      const keyVal = envRowValue(data.env_rows, 'SSL_KEY')
      if (keyVal) setSslKey(keyVal)
      const active = data.active_publish_mode
      if (active && data.publish_modes?.some((m) => m.key === active)) {
        setSelectedMode(active)
      } else if (data.publish_modes?.length) {
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

    const isUvicornHttps = selectedModeInfo.uses_uvicorn_https_port === true
    const port = Number(backendPort)
    const httpsPort = Number(isUvicornHttps ? backendPort : httpsPublicPort)
    const httpPort = Number(httpAcmePort)
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      notifyError(
        isUvicornHttps
          ? 'Укажите корректный HTTPS-порт (от 1 до 65535)'
          : 'Укажите корректный порт приложения (от 1 до 65535)',
      )
      return
    }
    if (selectedModeInfo.uses_nginx_ports) {
      if (!Number.isInteger(httpsPort) || httpsPort < 1 || httpsPort > 65535) {
        notifyError('Укажите корректный порт HTTPS')
        return
      }
      if (port === httpsPort || port === httpPort) {
        notifyError('Порт приложения не должен совпадать с публичными портами Nginx')
        return
      }
    }
    if (selectedModeInfo.requires_domain && !domain.trim()) {
      notifyError('Укажите адрес сайта (домен)')
      return
    }
    if (selectedModeInfo.requires_ssl_cert) {
      if (!sslCert.trim() || !sslKey.trim()) {
        notifyError('Укажите пути к сертификату и приватному ключу')
        return
      }
    }

    const isDirectHttp = selectedMode === 'http_direct'
    const isUvicorn = selectedMode.startsWith('uvicorn_')
    confirm({
      title: 'Применить настройки доступа?',
      description: `Выбран режим: ${selectedModeInfo.title}. Сайт может быть недоступен несколько минут.`,
      alert: {
        variant: isDirectHttp ? 'danger' : 'warning',
        title: isDirectHttp ? 'Небезопасный режим' : 'Изменение способа доступа',
        children: isDirectHttp
          ? (selectedModeInfo.warning ||
            'Открывать панель напрямую по HTTP из интернета небезопасно. Включите ограничение по IP в разделе «Защита входа».')
          : isUvicorn
            ? 'Будет настроен HTTPS на uvicorn (без Nginx). После обновления cert перезапустите панель.'
            : 'Будет настроен Nginx и защищённое соединение. Убедитесь, что домен указывает на этот сервер и порты открыты.',
      },
      confirmLabel: 'Применить',
      destructive: isDirectHttp,
      onConfirm: async () => {
        setPublishing(true)
        try {
          const resp = await publishVpnNetwork({
            mode: selectedMode as VpnNetworkPublishModeKey,
            backend_port: port,
            domain: domain.trim() || null,
            email: email.trim() || null,
            https_public_port: httpsPort,
            http_acme_port: httpPort,
            ssl_cert: sslCert.trim() || null,
            ssl_key: sslKey.trim() || null,
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
    return <Spinner label="Загрузка настроек сайта..." className="py-12" />
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
  const showNginxPorts = selectedModeInfo?.uses_nginx_ports === true
  const showUvicornHttpsPort = selectedModeInfo?.uses_uvicorn_https_port === true
  const showLetsEncryptEmail = selectedMode === 'nginx_le' || selectedMode === 'uvicorn_le'
  const showSslPaths = selectedModeInfo?.requires_ssl_cert === true
  const domainRow = settings.env_rows.find((r) => r.label.includes('DOMAIN'))
  const domainDisplay =
    domainRow && domainRow.value !== '—' ? domainRow.value : domain.trim() || 'не задан'

  return (
    <div className="space-y-4">
      <InlineProgressBar active={publishing} label="Применение настроек..." />
      <ConfirmDialogHost {...dialogProps} />

      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 md:col-span-2">
          <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-2xl" />
          <div className="relative grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricPill
              icon={publishModeIcon(settings.mode_key)}
              label="Режим"
              value={modeLabel}
              tone={
                settings.mode_key === 'reverse_proxy' ||
                settings.mode_key === 'nginx_le' ||
                settings.mode_key === 'direct_https'
                  ? 'success'
                  : 'default'
              }
            />
            <MetricPill icon={Globe} label="Домен" value={domainDisplay} />
            <MetricPill icon={Server} label="Порт приложения" value={settings.backend_port || backendPort} />
            <MetricPill
              icon={ExternalLink}
              label="Адресов"
              value={settings.primary_urls.length > 0 ? String(settings.primary_urls.length) : '—'}
              tone={settings.primary_urls.length > 0 ? 'success' : 'muted'}
            />
          </div>
        </div>

        <SectionHeading
          title="Текущий доступ"
          description="Как панель открывается сейчас и по каким адресам"
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div
            className={cn(
              'h-1 bg-gradient-to-r',
              settings.mode_key === 'reverse_proxy' ||
              settings.mode_key === 'nginx_le' ||
              settings.mode_key === 'direct_https'
                ? 'from-emerald-500/70 to-emerald-500/15'
                : 'from-sky-500/70 to-sky-500/15',
            )}
          />
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={modeBadgeVariant(settings.mode_key)}>{modeLabel}</Badge>
              <CardTitle className="text-base">{settings.mode_title}</CardTitle>
            </div>
            <CardDescription className="mt-1.5">
              Панель может открываться напрямую по порту или через веб-сервер с защищённым HTTPS
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 lg:grid-cols-[1fr_minmax(240px,300px)]">
            <ul className="space-y-2">
              {settings.bullet_points.map((point) => (
                <li
                  key={point}
                  className="flex gap-2 rounded-lg border bg-muted/20 px-3 py-2 text-sm text-muted-foreground"
                >
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                  <span>{point}</span>
                </li>
              ))}
            </ul>
            <aside className="space-y-4 rounded-xl border bg-muted/20 p-4">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Внутренний адрес
                </p>
                <code className="mt-1.5 block break-all rounded-lg bg-card/80 px-2.5 py-2 font-mono text-xs">
                  {settings.internal_url}
                </code>
              </div>
              {settings.primary_urls.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Откройте в браузере
                  </p>
                  {settings.primary_urls.map((row) => (
                    <a
                      key={row.url}
                      href={row.url}
                      className="flex flex-col gap-0.5 rounded-lg border bg-card/60 px-3 py-2 transition-colors hover:border-primary/30 hover:bg-primary/5"
                      title={row.label}
                    >
                      <span className="text-[11px] text-muted-foreground">{row.label}</span>
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

        <SectionHeading
          title="Параметры сервера"
          description="Справочно: значения из файла настроек на сервере"
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-violet-500/70 to-violet-500/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Globe size={18} />
              Текущие параметры
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-2 sm:grid-cols-2">
              {settings.env_rows.map((row) => (
                <div
                  key={row.label}
                  className="rounded-xl border bg-card/50 px-3 py-2.5"
                >
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    {row.label}
                  </dt>
                  <dd className="mt-1 text-sm">
                    {row.mono ? (
                      <code className="break-all rounded-md bg-muted/50 px-1.5 py-0.5 font-mono text-xs">
                        {row.value}
                      </code>
                    ) : (
                      row.value
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>

        <SectionHeading
          title="Мастер настройки"
          description="Выберите способ открытия панели в браузере и примените изменения"
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-primary/80 to-primary/15" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Rocket size={18} />
              Настроить доступ к панели
            </CardTitle>
            <CardDescription>Выберите режим и укажите домен при необходимости</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {(settings.publish_modes || []).map((mode) => {
                const Icon = publishModeIcon(mode.key)
                const selected = selectedMode === mode.key
                return (
                  <button
                    key={mode.key}
                    type="button"
                    onClick={() => setSelectedMode(mode.key)}
                    className={cn(
                      'flex flex-col gap-3 rounded-xl border p-4 text-left transition-all',
                      selected
                        ? 'border-primary bg-primary/5 ring-1 ring-primary'
                        : 'bg-card/50 hover:border-muted-foreground/30 hover:bg-muted/30',
                    )}
                  >
                    <div
                      className={cn(
                        'flex h-9 w-9 items-center justify-center rounded-lg',
                        selected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
                      )}
                    >
                      <Icon size={18} />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{mode.title}</p>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{mode.description}</p>
                    </div>
                  </button>
                )
              })}
            </div>

            {selectedModeInfo?.warning && (
              <SettingsAlert variant="warning" title="Внимание">
                {selectedModeInfo.warning}
              </SettingsAlert>
            )}

            <div className="rounded-xl border bg-muted/20 p-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="vpn-backend-port">
                    {showUvicornHttpsPort ? 'Порт HTTPS (uvicorn)' : 'Порт приложения'}
                  </Label>
                  <Input
                    id="vpn-backend-port"
                    type="number"
                    min={1}
                    max={65535}
                    value={backendPort}
                    onChange={(e) => setBackendPort(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    {showUvicornHttpsPort
                      ? 'Uvicorn слушает этот порт с TLS (например 8443 или 443)'
                      : 'Обычно 8000 — внутренний порт, на котором работает панель'}
                  </p>
                </div>
                {selectedModeInfo?.requires_domain && (
                  <div className="space-y-2">
                    <Label htmlFor="vpn-domain">Адрес сайта (домен)</Label>
                    <Input
                      id="vpn-domain"
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      placeholder="panel.example.com"
                      className="font-mono"
                    />
                  </div>
                )}
                {showLetsEncryptEmail && (
                  <div className="space-y-2">
                    <Label htmlFor="vpn-email">Email для сертификата</Label>
                    <Input
                      id="vpn-email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="admin@example.com"
                    />
                    <p className="text-xs text-muted-foreground">
                      Нужен для бесплатного HTTPS-сертификата Let&apos;s Encrypt
                    </p>
                  </div>
                )}
                {showSslPaths && (
                  <>
                    <div className="space-y-2 sm:col-span-2">
                      <Label htmlFor="vpn-ssl-cert">Путь к сертификату (.pem / .crt)</Label>
                      <Input
                        id="vpn-ssl-cert"
                        value={sslCert}
                        onChange={(e) => setSslCert(e.target.value)}
                        placeholder="/path/to/fullchain.pem"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div className="space-y-2 sm:col-span-2">
                      <Label htmlFor="vpn-ssl-key">Путь к приватному ключу (.key)</Label>
                      <Input
                        id="vpn-ssl-key"
                        value={sslKey}
                        onChange={(e) => setSslKey(e.target.value)}
                        placeholder="/path/to/privkey.pem"
                        className="font-mono text-xs"
                      />
                    </div>
                  </>
                )}
                {showNginxPorts && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="vpn-https-port">Публичный порт HTTPS (Nginx)</Label>
                      <Input
                        id="vpn-https-port"
                        type="number"
                        min={1}
                        max={65535}
                        value={httpsPublicPort}
                        onChange={(e) => setHttpsPublicPort(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">
                        Обычно 443 — защищённое соединение в браузере
                      </p>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="vpn-http-port">Порт HTTP (ACME / редирект)</Label>
                      <Input
                        id="vpn-http-port"
                        type="number"
                        min={1}
                        max={65535}
                        value={httpAcmePort}
                        onChange={(e) => setHttpAcmePort(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">
                        Обычно 80 — для проверки домена при выпуске сертификата
                      </p>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="flex justify-end border-t pt-4">
              <Button
                onClick={handlePublish}
                disabled={publishing || backgroundTaskPolling}
                className="gap-1.5"
                size="lg"
              >
                <Rocket size={18} className={publishing ? 'animate-pulse' : ''} />
                {publishing ? 'Применение...' : 'Применить настройки'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <SectionHeading
          title="Ручная настройка"
          description="Если мастер не подходит — команда для терминала на сервере"
        />

        <Card className="overflow-hidden shadow-sm md:col-span-2">
          <div className="h-1 bg-gradient-to-r from-muted-foreground/40 to-muted/10" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Terminal size={18} />
              Настройка вручную на сервере
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <code className="block rounded-xl border bg-muted/30 px-4 py-3 font-mono text-xs leading-relaxed">
              sudo ./{settings.nginx_setup_hint}
            </code>
            <p className="text-sm text-muted-foreground">
              Подробная инструкция — в файле README на сервере, раздел про Nginx и HTTPS.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
