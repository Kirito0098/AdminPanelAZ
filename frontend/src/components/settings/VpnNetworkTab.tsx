import { useCallback, useEffect, useRef, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  ExternalLink,
  Globe,
  Lock,
  Server,
  Shield,
  Terminal,
  Wifi,
} from 'lucide-react'
import { ApiError, getBackgroundTask, getBackgroundTaskForApiBase, getVpnNetworkDomainSsl, getVpnNetworkPortStatus, getVpnNetworkSettings, publishVpnNetwork } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import PublishAccessWizard from '@/components/settings/PublishAccessWizard'
import PublishAwaitDialog, { type PublishAwaitDialogState } from '@/components/settings/PublishAwaitDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { cn } from '@/lib/utils'
import type {
  VpnNetworkPortStatus,
  VpnNetworkPublishMode,
  VpnNetworkPublishModeKey,
  VpnNetworkDomainSslStatus,
  VpnNetworkSettings,
} from '@/types'
import {
  buildPublishConfirmPlan,
  domainFromSslSuggestion,
  guessPublishAccessUrl,
  inlinePublishWarnings,
  isPublishPathMovedPollMessage,
  isPublishStartTransientError,
  isPublishTransientRestartError,
  formatPublishStartError,
  publishConflictTaskId,
  PUBLISH_START_LOST_CONNECTION_NOTICE,
  resolvePublishTaskErrorMessage,
} from '@/components/settings/publishWizardUi'
import { apiBase, apiBaseForAccessPath, normalizeAccessPathInput } from '@/lib/panelBase'

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

function modeBadgeVariant(settings: VpnNetworkSettings): 'default' | 'secondary' | 'outline' | 'success' {
  const active = settings.active_publish_mode
  if (active?.startsWith('nginx_') && active !== 'nginx_selfsigned') return 'success'
  if (
    active?.startsWith('uvicorn_') &&
    active !== 'uvicorn_selfsigned' &&
    active !== 'http_direct'
  ) {
    return 'success'
  }
  if (settings.mode_key === 'reverse_proxy' || settings.mode_key === 'direct_https') return 'success'
  if (settings.mode_key === 'direct_http' || active === 'http_direct') return 'secondary'
  return 'outline'
}

function isSecurePublishTone(settings: VpnNetworkSettings): boolean {
  return modeBadgeVariant(settings) === 'success'
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

const PUBLISH_MODE_GROUPS: Array<{ id: string; title: string; keys: string[] }> = [
  {
    id: 'nginx',
    title: 'Через Nginx',
    keys: ['nginx_le', 'nginx_custom', 'nginx_selfsigned'],
  },
  {
    id: 'uvicorn',
    title: 'Напрямую на uvicorn (без Nginx)',
    keys: ['uvicorn_le', 'uvicorn_custom', 'uvicorn_selfsigned', 'http_direct'],
  },
]

function orderPublishModes(modes: VpnNetworkPublishMode[]): VpnNetworkPublishMode[] {
  const byKey = new Map(modes.map((mode) => [mode.key, mode]))
  const ordered: VpnNetworkPublishMode[] = []
  for (const group of PUBLISH_MODE_GROUPS) {
    for (const key of group.keys) {
      const mode = byKey.get(key)
      if (mode) ordered.push(mode)
    }
  }
  for (const mode of modes) {
    if (!ordered.some((entry) => entry.key === mode.key)) ordered.push(mode)
  }
  return ordered
}

export default function VpnNetworkTab() {
  const { error: notifyError } = useNotifications()
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
  const [accessPath, setAccessPath] = useState('')
  const [nginxSubpathIntegrate, setNginxSubpathIntegrate] = useState(false)
  const [publishAwait, setPublishAwait] = useState<PublishAwaitDialogState | null>(null)
  const [domainSslStatus, setDomainSslStatus] = useState<VpnNetworkDomainSslStatus | null>(null)
  const [portStatuses, setPortStatuses] = useState<Record<string, VpnNetworkPortStatus | null>>({})
  const userPickedModeRef = useRef(false)
  const hasSettingsRef = useRef(false)
  const suppressSslAutofillRef = useRef(false)
  const domainSslSeqRef = useRef(0)
  const portStatusSeqRef = useRef(0)
  const notifyErrorRef = useRef(notifyError)
  notifyErrorRef.current = notifyError

  const loadSettings = useCallback(async (options?: { syncSelectedMode?: boolean }) => {
    const syncSelectedMode = options?.syncSelectedMode ?? false
    const isInitialLoad = !hasSettingsRef.current
    if (!hasSettingsRef.current) {
      setLoading(true)
    }
    setLoadError(null)
    try {
      const data = await getVpnNetworkSettings()
      setSettings(data)
      hasSettingsRef.current = true
      if (
        isInitialLoad &&
        (data.shared_domain_status_openvpn || data.shared_domain_foreign_vhost)
      ) {
        setNginxSubpathIntegrate(true)
      }
      setBackendPort(data.backend_port || '8000')
      setDomain(envRowValue(data.env_rows, 'DOMAIN'))
      setHttpsPublicPort(envRowValue(data.env_rows, 'HTTPS_PUBLIC_PORT') || '443')
      setHttpAcmePort(envRowValue(data.env_rows, 'HTTP_ACME_PORT') || '80')
      const certVal = data.known_ssl_cert || envRowValue(data.env_rows, 'SSL_CERT')
      setSslCert(certVal)
      const keyVal = data.known_ssl_key || envRowValue(data.env_rows, 'SSL_KEY')
      setSslKey(keyVal)
      suppressSslAutofillRef.current = Boolean(certVal && keyVal)
      const accessPathVal = envRowValue(data.env_rows, 'ACCESS_PATH')
      setAccessPath(accessPathVal)
      if (syncSelectedMode && !userPickedModeRef.current) {
        const active = data.active_publish_mode
        if (active && data.publish_modes?.some((m) => m.key === active)) {
          setSelectedMode(active)
        } else if (data.publish_modes?.length) {
          setSelectedMode(data.publish_modes[0].key)
        }
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Ошибка загрузки'
      setLoadError(message)
      notifyErrorRef.current(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSettings({ syncSelectedMode: true })
  }, [loadSettings])

  useEffect(() => {
    const host = domain.trim().split(':')[0]
    if (!host) {
      setDomainSslStatus(null)
      return
    }
    const seq = ++domainSslSeqRef.current
    const timer = window.setTimeout(() => {
      void getVpnNetworkDomainSsl(host)
        .then((data) => {
          if (seq === domainSslSeqRef.current) setDomainSslStatus(data)
        })
        .catch(() => {
          if (seq === domainSslSeqRef.current) setDomainSslStatus(null)
        })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [domain])

  const selectedModeInfo: VpnNetworkPublishMode | undefined = settings?.publish_modes?.find(
    (m) => m.key === selectedMode,
  )

  useEffect(() => {
    const usesNginxPorts = selectedModeInfo?.uses_nginx_ports === true
    const checks: Array<{ key: string; port: number; role: 'backend' | 'nginx_https' | 'nginx_http' }> = []
    const backend = Number(backendPort)
    if (Number.isInteger(backend) && backend >= 1 && backend <= 65535) {
      checks.push({ key: 'backend', port: backend, role: 'backend' })
    }
    if (usesNginxPorts) {
      const https = Number(httpsPublicPort)
      const http = Number(httpAcmePort)
      if (Number.isInteger(https) && https >= 1 && https <= 65535) {
        checks.push({ key: 'nginx_https', port: https, role: 'nginx_https' })
      }
      if (Number.isInteger(http) && http >= 1 && http <= 65535) {
        checks.push({ key: 'nginx_http', port: http, role: 'nginx_http' })
      }
    }

    if (checks.length === 0) {
      setPortStatuses({})
      return
    }

    const seq = ++portStatusSeqRef.current
    const timer = window.setTimeout(() => {
      void Promise.all(
        checks.map(async (check) => {
          try {
            const data = await getVpnNetworkPortStatus(check.port, check.role)
            return [check.key, data] as const
          } catch {
            return [check.key, null] as const
          }
        }),
      ).then((entries) => {
        if (seq !== portStatusSeqRef.current) return
        setPortStatuses(Object.fromEntries(entries))
      })
    }, 350)

    return () => window.clearTimeout(timer)
  }, [backendPort, httpsPublicPort, httpAcmePort, selectedModeInfo?.uses_nginx_ports])

  useEffect(() => {
    if (!selectedModeInfo?.requires_ssl_cert || !settings) return
    if (suppressSslAutofillRef.current) return
    if (sslCert.trim() && sslKey.trim()) return
    if (settings.known_ssl_cert && settings.known_ssl_key) {
      setSslCert(settings.known_ssl_cert)
      setSslKey(settings.known_ssl_key)
    }
  }, [
    selectedMode,
    selectedModeInfo?.requires_ssl_cert,
    settings?.known_ssl_cert,
    settings?.known_ssl_key,
    settings,
  ])

  const handlePublish = () => {
    if (!selectedModeInfo) {
      notifyError('Режим публикации не выбран или не загружен')
      return
    }

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
      if (!Number.isInteger(httpPort) || httpPort < 1 || httpPort > 65535) {
        notifyError('Укажите корректный порт HTTP (ACME)')
        return
      }
      if (port === httpsPort || port === httpPort) {
        notifyError('Порт приложения не должен совпадать с публичными портами Nginx')
        return
      }
      if (httpPort === httpsPort) {
        notifyError('Порт HTTP (ACME) не должен совпадать с портом HTTPS')
        return
      }
    }
    if (selectedModeInfo.requires_domain && !domain.trim()) {
      notifyError('Укажите адрес сайта (домен)')
      return
    }
    if (selectedModeInfo.requires_ssl_cert) {
      const hasPaths = sslCert.trim() && sslKey.trim()
      const hasKnown = Boolean(settings?.known_ssl_cert && settings?.known_ssl_key)
      const hasSuggestions = (settings?.ssl_cert_suggestions?.length ?? 0) > 0
      if (!hasPaths && !hasKnown && !hasSuggestions) {
        notifyError('Укажите пути к сертификату и приватному ключу')
        return
      }
    }
    if (accessPath.trim() && !selectedMode.startsWith('nginx_')) {
      notifyError('Путь доступа (ACCESS_PATH) поддерживается только с режимами Nginx')
      return
    }

    const confirmPlan = buildPublishConfirmPlan(
      selectedMode,
      selectedModeInfo,
      settings,
      domain,
      backendPort,
      httpsPublicPort,
      domainLetsEncrypt,
      accessPath,
      nginxSubpathIntegrate,
    )
    confirm({
      title: 'Применить настройки доступа?',
      description: (
        <span>
          Режим: <strong>{selectedModeInfo.title}</strong>. Изменения займут 1–3 минуты.
        </span>
      ),
      alert: {
        variant: confirmPlan.alertVariant,
        title: confirmPlan.alertTitle,
        children: (
          <ul className="list-disc space-y-1.5 pl-4 text-sm leading-relaxed">
            {confirmPlan.bullets.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ),
      },
      children: (
        <div className="rounded-lg border bg-muted/25 px-3 py-2.5 text-sm">
          <dl className="grid gap-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <dt className="text-muted-foreground">Домен</dt>
              <dd className="font-mono text-xs">{domain.trim() || '—'}</dd>
            </div>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <dt className="text-muted-foreground">Порт приложения</dt>
              <dd className="font-mono text-xs">{backendPort}</dd>
            </div>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <dt className="text-muted-foreground">Путь доступа</dt>
              <dd className="font-mono text-xs">{accessPath.trim() || '/'}</dd>
            </div>
            {confirmPlan.accessUrl && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                  <dt className="text-muted-foreground">Адрес после применения</dt>
                  <dd className="break-all font-mono text-xs text-primary">{confirmPlan.accessUrl}</dd>
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Откройте этот адрес вручную после завершения. Если не загрузится — подождите до 5 минут.
                </p>
              </div>
            )}
          </dl>
        </div>
      ),
      confirmLabel: 'Применить',
      destructive: confirmPlan.destructive,
      onConfirm: async () => {
        userPickedModeRef.current = false
        const expectedAccessUrl = confirmPlan.accessUrl?.trim() || ''
        const fallbackApiBase = accessPath.trim() ? apiBaseForAccessPath(accessPath) : null
        const publishTaskFetcher = async (taskId: string) => {
          try {
            return await getBackgroundTask(taskId)
          } catch (err) {
            if (
              fallbackApiBase &&
              fallbackApiBase !== apiBase &&
              err instanceof ApiError &&
              (err.status === 404 || err.status === 502 || err.status === 503)
            ) {
              return await getBackgroundTaskForApiBase(taskId, fallbackApiBase)
            }
            throw err
          }
        }
        const publishPollOptions = {
          showProgress: false as const,
          fetchTask: fallbackApiBase && fallbackApiBase !== apiBase ? publishTaskFetcher : undefined,
          formatPollError: (message: string) => resolvePublishTaskErrorMessage(message, expectedAccessUrl),
          isTransientPollError: (err: unknown, message: string) =>
            isPublishTransientRestartError(err, message) ||
            isPublishPathMovedPollMessage(message, expectedAccessUrl),
        }
        const startPublishTracking = (taskId: string, fallbackMessage?: string) => {
          setPublishAwait({ accessUrl: expectedAccessUrl, status: 'running' })
          trackBackgroundTask(taskId, {
            ...publishPollOptions,
            onComplete: (task) => {
              const result = task?.result as
                | {
                    requires_manual_restart?: boolean
                    panel_restarted?: boolean
                    restart_command?: string
                    access_url?: string
                  }
                | undefined
              const restartCmd =
                result?.restart_command || settings?.panel_restart_command || 'sudo systemctl restart adminpanelaz'
              const accessUrl = result?.access_url?.trim() || expectedAccessUrl
              const baseMessage = task?.message || fallbackMessage || 'Публикация завершена'
              setPublishAwait({
                accessUrl,
                status: 'completed',
                message: result?.requires_manual_restart
                  ? `${baseMessage}. Выполните: ${restartCmd}`
                  : baseMessage,
                restartCommand: result?.requires_manual_restart ? restartCmd : undefined,
              })
              userPickedModeRef.current = false
              void loadSettings({ syncSelectedMode: true })
            },
            onError: (task, message) => {
              if (task?.status === 'failed') {
                setPublishAwait({
                  accessUrl: expectedAccessUrl,
                  status: 'failed',
                  message: task.error || task.message || message,
                })
                return
              }
              if (
                expectedAccessUrl &&
                (isPublishPathMovedPollMessage(message, expectedAccessUrl) ||
                  isPublishTransientRestartError(null, message))
              ) {
                return
              }
              setPublishAwait({
                accessUrl: expectedAccessUrl,
                status: 'failed',
                message: task?.error || task?.message || message,
              })
            },
          })
        }
        try {
          const resp = await publishVpnNetwork({
            mode: selectedMode as VpnNetworkPublishModeKey,
            backend_port: port,
            domain: domain.trim().split(':')[0] || null,
            email: email.trim() || null,
            https_public_port: httpsPort,
            http_acme_port: httpPort,
            ssl_cert: sslCert.trim() || null,
            ssl_key: sslKey.trim() || null,
            access_path: accessPath.trim() || null,
            nginx_subpath_integrate: nginxSubpathIntegrate,
          })
          startPublishTracking(resp.task_id, resp.message)
        } catch (err) {
          const conflictTaskId = publishConflictTaskId(err)
          if (conflictTaskId) {
            startPublishTracking(conflictTaskId)
            return
          }
          if (isPublishStartTransientError(err)) {
            setPublishAwait({
              accessUrl: expectedAccessUrl,
              status: 'running',
              message: PUBLISH_START_LOST_CONNECTION_NOTICE,
              allowDismissWhileRunning: true,
            })
            return
          }
          setPublishAwait({
            accessUrl: expectedAccessUrl,
            status: 'failed',
            message: formatPublishStartError(err),
          })
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
  const uvicornWarnings = inlinePublishWarnings(selectedMode, settings, domain)
  const domainLetsEncrypt = domainSslStatus?.has_letsencrypt ?? null
  const orderedPublishModes = orderPublishModes(settings.publish_modes || [])
  const previewAccessUrl = guessPublishAccessUrl(
    selectedMode,
    domain,
    backendPort,
    httpsPublicPort,
    settings,
    domainLetsEncrypt,
    accessPath,
  )
  const showAccessPathField = selectedMode.startsWith('nginx_')
  const domainHostForShared = domain.trim().split(':')[0]
  const sharedDomainForeignVhost = domainHostForShared
    ? Boolean(domainSslStatus?.shared_domain_foreign_vhost)
    : Boolean(settings.shared_domain_foreign_vhost)
  const sharedDomainStatusOpenVpn = domainHostForShared
    ? Boolean(domainSslStatus?.shared_domain_status_openvpn)
    : Boolean(settings.shared_domain_status_openvpn)
  const showGenericSubpathIntegrate =
    showAccessPathField &&
    Boolean(accessPath.trim()) &&
    sharedDomainForeignVhost &&
    !sharedDomainStatusOpenVpn
  const showStatusOpenVpnIntegrate =
    showAccessPathField && Boolean(accessPath.trim()) && sharedDomainStatusOpenVpn
  const showOptionalDomain =
    !selectedModeInfo?.requires_domain &&
    (selectedMode === 'uvicorn_custom' ||
      selectedMode === 'nginx_custom' ||
      selectedMode === 'uvicorn_selfsigned' ||
      selectedMode === 'nginx_selfsigned')
  const selfsignedDomainHint =
    selectedMode === 'uvicorn_selfsigned' || selectedMode === 'nginx_selfsigned'
  const domainRow = settings.env_rows.find((r) => r.label.includes('DOMAIN'))
  const domainDisplay =
    domainRow && domainRow.value !== '—' ? domainRow.value : domain.trim() || 'не задан'

  return (
    <div className="space-y-4">
      <PublishAwaitDialog state={publishAwait} onDismiss={() => setPublishAwait(null)} />
      <ConfirmDialogHost dialogProps={dialogProps} />

      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 md:col-span-2">
          <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-primary/10 blur-2xl" />
          <div className="relative grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricPill
              icon={publishModeIcon(settings.mode_key)}
              label="Режим"
              value={modeLabel}
              tone={isSecurePublishTone(settings) ? 'success' : 'default'}
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
              isSecurePublishTone(settings)
                ? 'from-emerald-500/70 to-emerald-500/15'
                : 'from-sky-500/70 to-sky-500/15',
            )}
          />
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={modeBadgeVariant(settings)}>{modeLabel}</Badge>
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

        <PublishAccessWizard
          settings={settings}
          publishModes={orderedPublishModes}
          selectedMode={selectedMode}
          onSelectMode={(modeKey) => {
            userPickedModeRef.current = true
            if (!modeKey.startsWith('nginx_') && selectedMode.startsWith('nginx_')) {
              setAccessPath('')
            }
            suppressSslAutofillRef.current = false
            setSelectedMode(modeKey)
          }}
          selectedModeInfo={selectedModeInfo}
          backendPort={backendPort}
          onBackendPortChange={setBackendPort}
          domain={domain}
          onDomainChange={setDomain}
          email={email}
          onEmailChange={setEmail}
          httpsPublicPort={httpsPublicPort}
          onHttpsPublicPortChange={setHttpsPublicPort}
          httpAcmePort={httpAcmePort}
          onHttpAcmePortChange={setHttpAcmePort}
          sslCert={sslCert}
          onSslCertChange={(value) => {
            suppressSslAutofillRef.current = true
            setSslCert(value)
          }}
          sslKey={sslKey}
          onSslKeyChange={(value) => {
            suppressSslAutofillRef.current = true
            setSslKey(value)
          }}
          accessPath={accessPath}
          onAccessPathChange={setAccessPath}
          onAccessPathBlur={() => setAccessPath((value) => normalizeAccessPathInput(value))}
          nginxSubpathIntegrate={nginxSubpathIntegrate}
          onIntegrateChange={setNginxSubpathIntegrate}
          portStatuses={portStatuses}
          domainSslStatus={domainSslStatus}
          previewAccessUrl={previewAccessUrl}
          uvicornWarnings={uvicornWarnings}
          publishing={backgroundTaskPolling}
          onPublish={handlePublish}
          showUvicornHttpsPort={showUvicornHttpsPort}
          showLetsEncryptEmail={showLetsEncryptEmail}
          showSslPaths={showSslPaths}
          showNginxPorts={showNginxPorts}
          showAccessPathField={showAccessPathField}
          showStatusOpenVpnIntegrate={showStatusOpenVpnIntegrate}
          showGenericSubpathIntegrate={showGenericSubpathIntegrate}
          showOptionalDomain={showOptionalDomain}
          selfsignedDomainHint={selfsignedDomainHint}
          onPickSslSuggestion={(cert, key) => {
            setSslCert(cert)
            setSslKey(key)
            const item = settings.ssl_cert_suggestions?.find((entry) => entry.cert === cert)
            if (item) {
              const suggestedDomain = domainFromSslSuggestion(item)
              if (suggestedDomain) setDomain(suggestedDomain)
            }
          }}
        />

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
