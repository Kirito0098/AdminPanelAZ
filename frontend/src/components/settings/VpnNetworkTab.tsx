import { useCallback, useEffect, useRef, useState } from 'react'
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
import { ApiError, getBackgroundTask, getBackgroundTaskForApiBase, getVpnNetworkDomainSsl, getVpnNetworkPortStatus, getVpnNetworkSettings, publishVpnNetwork } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import PublishAwaitDialog, { type PublishAwaitDialogState } from '@/components/settings/PublishAwaitDialog'
import SharedDomainPublishSection from '@/components/settings/SharedDomainPublishSection'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
  parsePublishModeWarning,
  publishAddressHint,
  shouldShowAddressHint,
  publishModeWarningTitle,
  publishModeWarningVariant,
  publishUvicornWarningsTitle,
  getLetsEncryptPathsForDomain,
  guessPublishAccessUrl,
  hasLetsEncryptHint,
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

function publishModeMethodLabel(mode: VpnNetworkPublishMode): string | null {
  if (mode.method) return mode.method
  if (mode.key.startsWith('nginx_')) return 'Nginx'
  if (mode.key.startsWith('uvicorn_') || mode.key === 'http_direct') return 'Uvicorn'
  return null
}

function PortStatusHint({ status }: { status: VpnNetworkPortStatus | null | undefined }) {
  if (!status) return null
  return (
    <p
      className={cn(
        'text-xs leading-relaxed',
        status.status === 'free' && 'text-muted-foreground',
        status.status === 'panel' && 'text-emerald-600 dark:text-emerald-400',
        status.status === 'nginx' && 'text-primary',
        status.status === 'other' && 'text-amber-600 dark:text-amber-400',
        status.status === 'unknown' && 'text-muted-foreground',
      )}
    >
      {status.message}
    </p>
  )
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
  const notifyErrorRef = useRef(notifyError)
  notifyErrorRef.current = notifyError

  const loadSettings = useCallback(async (options?: { syncSelectedMode?: boolean }) => {
    const syncSelectedMode = options?.syncSelectedMode ?? false
    if (!hasSettingsRef.current) {
      setLoading(true)
    }
    setLoadError(null)
    try {
      const data = await getVpnNetworkSettings()
      setSettings(data)
      hasSettingsRef.current = true
      if (data.shared_domain_status_openvpn || data.shared_domain_foreign_vhost) {
        setNginxSubpathIntegrate(true)
      }
      setBackendPort(data.backend_port || '8000')
      const domainVal = envRowValue(data.env_rows, 'DOMAIN')
      if (domainVal) setDomain(domainVal)
      const httpsPortVal = envRowValue(data.env_rows, 'HTTPS_PUBLIC_PORT')
      if (httpsPortVal) setHttpsPublicPort(httpsPortVal)
      const certVal = data.known_ssl_cert || envRowValue(data.env_rows, 'SSL_CERT')
      if (certVal) setSslCert(certVal)
      const keyVal = data.known_ssl_key || envRowValue(data.env_rows, 'SSL_KEY')
      if (keyVal) setSslKey(keyVal)
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
    const timer = window.setTimeout(() => {
      void getVpnNetworkDomainSsl(host)
        .then((data) => setDomainSslStatus(data))
        .catch(() => setDomainSslStatus(null))
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
        setPortStatuses(Object.fromEntries(entries))
      })
    }, 350)

    return () => window.clearTimeout(timer)
  }, [backendPort, httpsPublicPort, httpAcmePort, selectedModeInfo?.uses_nginx_ports])

  useEffect(() => {
    if (!selectedModeInfo?.requires_ssl_cert || !settings) return
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
    sslCert,
    sslKey,
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
            domain: domain.trim() || null,
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
  const modeWarningLines = parsePublishModeWarning(selectedModeInfo?.warning)
  const domainLetsEncrypt = domainSslStatus?.has_letsencrypt ?? null
  const foundLetsEncryptPaths = getLetsEncryptPathsForDomain(settings, domain, domainSslStatus)
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
  const showSubpathIntegrate =
    showAccessPathField &&
    Boolean(accessPath.trim()) &&
    settings.shared_domain_foreign_vhost &&
    !settings.shared_domain_status_openvpn
  const showStatusOpenVpnIntegrate =
    showAccessPathField && Boolean(accessPath.trim()) && settings.shared_domain_status_openvpn
  const showOptionalDomain =
    !selectedModeInfo?.requires_domain &&
    (selectedMode === 'uvicorn_custom' ||
      selectedMode === 'nginx_custom' ||
      selectedMode === 'uvicorn_selfsigned' ||
      selectedMode === 'nginx_selfsigned')
  const selfsignedDomainHint =
    selectedMode === 'uvicorn_selfsigned' || selectedMode === 'nginx_selfsigned'
  const orderedPublishModes = orderPublishModes(settings.publish_modes || [])
  const addressHint = publishAddressHint(selectedMode)
  const showAddressHint = shouldShowAddressHint(selectedMode) && addressHint.lines.length > 0
  const showServerUvicornHints =
    uvicornWarnings.length > 0 &&
    (selectedMode === 'uvicorn_le' || selectedMode === 'uvicorn_custom')
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
            <CardDescription>Выберите режим и укажите домен или пути к сертификатам</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {PUBLISH_MODE_GROUPS.map((group) => {
              const groupModes = group.keys
                .map((key) => orderedPublishModes.find((mode) => mode.key === key))
                .filter((mode): mode is VpnNetworkPublishMode => Boolean(mode))
              if (groupModes.length === 0) return null
              return (
                <div key={group.id} className="space-y-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {group.title}
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {groupModes.map((mode) => {
                      const Icon = publishModeIcon(mode.key)
                      const methodLabel = publishModeMethodLabel(mode)
                      const selected = selectedMode === mode.key
                      return (
                        <button
                          key={mode.key}
                          type="button"
                          onClick={() => {
                            userPickedModeRef.current = true
                            setSelectedMode(mode.key)
                          }}
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
                            {methodLabel && (
                              <p className="mt-0.5 text-[11px] font-semibold uppercase tracking-wide text-primary/80">
                                {methodLabel}
                              </p>
                            )}
                            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{mode.description}</p>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )
            })}

            {showAddressHint && (
              <SettingsAlert variant="info" title={addressHint.title}>
                <p className="text-sm leading-relaxed">{addressHint.lines[0]}</p>
              </SettingsAlert>
            )}

            {modeWarningLines.length > 0 && (
              <SettingsAlert
                variant={publishModeWarningVariant(selectedMode)}
                title={publishModeWarningTitle(selectedMode)}
              >
                <ul className="list-disc space-y-1 pl-4 text-sm leading-relaxed">
                  {modeWarningLines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </SettingsAlert>
            )}

            {selectedMode === 'nginx_le' && hasLetsEncryptHint(settings, domain, domainLetsEncrypt) && (
              <SettingsAlert variant="info" title="Сертификат найден">
                <p className="text-sm leading-relaxed">
                  Let&apos;s Encrypt для этого домена уже есть — будет переиспользован.
                </p>
                {foundLetsEncryptPaths && (
                  <p className="mt-1.5 break-all font-mono text-xs text-muted-foreground">
                    {foundLetsEncryptPaths.cert}
                  </p>
                )}
              </SettingsAlert>
            )}

            {showServerUvicornHints && (
              <SettingsAlert variant="info" title={publishUvicornWarningsTitle(selectedMode, uvicornWarnings)}>
                <ul className="list-disc space-y-1 pl-4">
                  {uvicornWarnings.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </SettingsAlert>
            )}

            {previewAccessUrl && !(showAccessPathField && accessPath.trim()) && (
              <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-sm">
                <span className="text-muted-foreground">После применения откройте: </span>
                <code className="break-all font-mono text-xs text-primary">{previewAccessUrl}</code>
                {selectedMode === 'http_direct' && (
                  <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                    В режиме HTTP домен из настроек не используется — только IP-адрес сервера.
                  </p>
                )}
              </div>
            )}

            {selectedModeInfo?.uses_nginx_ports && settings.nginx_installed === false && (
              <SettingsAlert variant="info" title="Nginx не установлен">
                Nginx будет установлен автоматически при применении настроек. Убедитесь, что порты 80/443 открыты.
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
                  <PortStatusHint status={portStatuses.backend} />
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
                {showOptionalDomain && (
                  <div className="space-y-2">
                    <Label htmlFor="vpn-domain-optional">
                      {selfsignedDomainHint ? 'Адрес сайта (домен или IP)' : 'Домен (необязательно)'}
                    </Label>
                    <Input
                      id="vpn-domain-optional"
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      placeholder={selfsignedDomainHint ? '192.168.1.10' : 'panel.example.com'}
                      className="font-mono"
                    />
                    <p className="text-xs text-muted-foreground">
                      {selfsignedDomainHint
                        ? 'Попадёт в CN самоподписанного сертификата. Без домена будет использован IP-адрес сервера.'
                        : 'Для подсказок URL и CORS; если уже задан в .env — можно оставить пустым'}
                    </p>
                  </div>
                )}
                {showAccessPathField && (
                  <SharedDomainPublishSection
                    domain={domain}
                    accessPath={accessPath}
                    previewAccessUrl={previewAccessUrl}
                    settings={settings}
                    nginxSubpathIntegrate={nginxSubpathIntegrate}
                    onAccessPathChange={setAccessPath}
                    onAccessPathBlur={() => setAccessPath((value) => normalizeAccessPathInput(value))}
                    onIntegrateChange={setNginxSubpathIntegrate}
                    showStatusOpenVpnIntegrate={showStatusOpenVpnIntegrate}
                    showGenericSubpathIntegrate={showSubpathIntegrate}
                  />
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
                  <div className="space-y-4 rounded-xl border border-primary/25 bg-primary/5 p-4 sm:col-span-2">
                    <div>
                      <p className="text-sm font-medium">Пути к сертификатам на сервере</p>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                        Укажите абсолютные пути к файлам сертификата или выберите найденный на сервере вариант.
                        Панель должна иметь право читать эти файлы.
                      </p>
                    </div>
                    {(settings.ssl_cert_suggestions?.length ?? 0) > 0 && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-muted-foreground">Найденные сертификаты</p>
                        <div className="flex flex-wrap gap-2">
                          {settings.ssl_cert_suggestions!.map((item) => (
                            <Button
                              key={`${item.source}-${item.cert}`}
                              type="button"
                              size="sm"
                              variant="outline"
                              className="h-auto max-w-full whitespace-normal text-left text-xs"
                              onClick={() => {
                                setSslCert(item.cert)
                                setSslKey(item.key)
                                const suggestedDomain = domainFromSslSuggestion(item)
                                if (suggestedDomain) setDomain(suggestedDomain)
                              }}
                            >
                              {item.label}
                            </Button>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="space-y-2">
                      <Label htmlFor="vpn-ssl-cert">Путь к сертификату (.pem / .crt)</Label>
                      <Input
                        id="vpn-ssl-cert"
                        value={sslCert}
                        onChange={(e) => setSslCert(e.target.value)}
                        placeholder="/etc/letsencrypt/live/your-domain/fullchain.pem"
                        className="font-mono text-xs"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="vpn-ssl-key">Путь к приватному ключу (.key)</Label>
                      <Input
                        id="vpn-ssl-key"
                        value={sslKey}
                        onChange={(e) => setSslKey(e.target.value)}
                        placeholder="/etc/letsencrypt/live/your-domain/privkey.pem"
                        className="font-mono text-xs"
                      />
                    </div>
                  </div>
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
                      <PortStatusHint status={portStatuses.nginx_https} />
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
                      <PortStatusHint status={portStatuses.nginx_http} />
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="flex justify-end border-t pt-4">
              <Button
                onClick={handlePublish}
                disabled={backgroundTaskPolling}
                className="gap-1.5"
                size="lg"
              >
                <Rocket size={18} className={backgroundTaskPolling ? 'animate-pulse' : ''} />
                {backgroundTaskPolling ? 'Применение...' : 'Применить настройки'}
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
