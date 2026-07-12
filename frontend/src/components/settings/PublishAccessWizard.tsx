import { useEffect, useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Check,
  ExternalLink,
  Globe,
  Lock,
  Rocket,
  Shield,
  Sparkles,
  Wifi,
} from 'lucide-react'
import SharedDomainPublishSection from '@/components/settings/SharedDomainPublishSection'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import {
  getLetsEncryptPathsForDomain,
  hasLetsEncryptHint,
  parsePublishModeWarning,
  publishAddressHint,
  publishModeWarningTitle,
  publishModeWarningVariant,
  publishUvicornWarningsTitle,
  shouldShowAddressHint,
} from '@/components/settings/publishWizardUi'
import type {
  VpnNetworkDomainSslStatus,
  VpnNetworkPortStatus,
  VpnNetworkPublishMode,
  VpnNetworkSettings,
} from '@/types'

const MODE_ICONS: Record<string, LucideIcon> = {
  http_direct: Wifi,
  nginx_le: Shield,
  nginx_selfsigned: Lock,
  nginx_custom: Lock,
  uvicorn_le: Shield,
  uvicorn_custom: Shield,
  uvicorn_selfsigned: Lock,
}

const PUBLISH_STACKS = [
  { id: 'nginx' as const, title: 'Через Nginx', hint: 'Рекомендуется для интернета', keys: ['nginx_le', 'nginx_custom', 'nginx_selfsigned'] },
  { id: 'uvicorn' as const, title: 'Напрямую на uvicorn', hint: 'Без reverse proxy', keys: ['uvicorn_le', 'uvicorn_custom', 'uvicorn_selfsigned', 'http_direct'] },
]

type PublishStackId = (typeof PUBLISH_STACKS)[number]['id']

function publishModeIcon(key: string): LucideIcon {
  return MODE_ICONS[key] ?? Globe
}

function publishModeMethodLabel(mode: VpnNetworkPublishMode): string | null {
  if (mode.method) return mode.method
  if (mode.key.startsWith('nginx_')) return 'Nginx'
  if (mode.key.startsWith('uvicorn_') || mode.key === 'http_direct') return 'Uvicorn'
  return null
}

function stackForMode(modeKey: string): PublishStackId {
  return modeKey.startsWith('nginx_') ? 'nginx' : 'uvicorn'
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

function FormSection({
  title,
  description,
  children,
  className,
}: {
  title: string
  description?: string
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('space-y-3', className)}>
      <div>
        <h4 className="text-sm font-medium">{title}</h4>
        {description ? <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  )
}

export type PublishAccessWizardProps = {
  settings: VpnNetworkSettings
  publishModes: VpnNetworkPublishMode[]
  selectedMode: string
  onSelectMode: (modeKey: string) => void
  selectedModeInfo?: VpnNetworkPublishMode
  backendPort: string
  onBackendPortChange: (value: string) => void
  domain: string
  onDomainChange: (value: string) => void
  email: string
  onEmailChange: (value: string) => void
  httpsPublicPort: string
  onHttpsPublicPortChange: (value: string) => void
  httpAcmePort: string
  onHttpAcmePortChange: (value: string) => void
  sslCert: string
  onSslCertChange: (value: string) => void
  sslKey: string
  onSslKeyChange: (value: string) => void
  accessPath: string
  onAccessPathChange: (value: string) => void
  onAccessPathBlur: () => void
  nginxSubpathIntegrate: boolean
  onIntegrateChange: (checked: boolean) => void
  portStatuses: Record<string, VpnNetworkPortStatus | null>
  domainSslStatus: VpnNetworkDomainSslStatus | null
  previewAccessUrl?: string
  uvicornWarnings: string[]
  publishing: boolean
  onPublish: () => void
  showUvicornHttpsPort: boolean
  showLetsEncryptEmail: boolean
  showSslPaths: boolean
  showNginxPorts: boolean
  showAccessPathField: boolean
  showStatusOpenVpnIntegrate: boolean
  showGenericSubpathIntegrate: boolean
  showOptionalDomain: boolean
  selfsignedDomainHint: boolean
  onPickSslSuggestion: (cert: string, key: string) => void
}

export default function PublishAccessWizard({
  settings,
  publishModes,
  selectedMode,
  onSelectMode,
  selectedModeInfo,
  backendPort,
  onBackendPortChange,
  domain,
  onDomainChange,
  email,
  onEmailChange,
  httpsPublicPort,
  onHttpsPublicPortChange,
  httpAcmePort,
  onHttpAcmePortChange,
  sslCert,
  onSslCertChange,
  sslKey,
  onSslKeyChange,
  accessPath,
  onAccessPathChange,
  onAccessPathBlur,
  nginxSubpathIntegrate,
  onIntegrateChange,
  portStatuses,
  domainSslStatus,
  previewAccessUrl,
  uvicornWarnings,
  publishing,
  onPublish,
  showUvicornHttpsPort,
  showLetsEncryptEmail,
  showSslPaths,
  showNginxPorts,
  showAccessPathField,
  showStatusOpenVpnIntegrate,
  showGenericSubpathIntegrate,
  showOptionalDomain,
  selfsignedDomainHint,
  onPickSslSuggestion,
}: PublishAccessWizardProps) {
  const [activeStack, setActiveStack] = useState<PublishStackId>(() => stackForMode(selectedMode))
  const domainLetsEncrypt = domainSslStatus?.has_letsencrypt ?? null
  const addressHint = publishAddressHint(selectedMode, httpsPublicPort)
  const showAddressHint = shouldShowAddressHint(selectedMode) && addressHint.lines.length > 0
  const modeWarningLines = parsePublishModeWarning(selectedModeInfo?.warning)
  const showServerUvicornHints =
    uvicornWarnings.length > 0 && (selectedMode === 'uvicorn_le' || selectedMode === 'uvicorn_custom')
  const foundLetsEncryptPaths = getLetsEncryptPathsForDomain(settings, domain, domainSslStatus)

  useEffect(() => {
    setActiveStack(stackForMode(selectedMode))
  }, [selectedMode])

  const stackModes = PUBLISH_STACKS.find((stack) => stack.id === activeStack)?.keys ?? []
  const visibleModes = stackModes
    .map((key) => publishModes.find((mode) => mode.key === key))
    .filter((mode): mode is VpnNetworkPublishMode => Boolean(mode))

  const handleStackChange = (stackId: PublishStackId) => {
    setActiveStack(stackId)
    const stack = PUBLISH_STACKS.find((item) => item.id === stackId)
    if (!stack) return
    if (stack.keys.includes(selectedMode)) return
    const first = stack.keys.map((key) => publishModes.find((mode) => mode.key === key)).find(Boolean)
    if (first) onSelectMode(first.key)
  }

  return (
    <Card className="flex max-h-[90dvh] flex-col overflow-hidden shadow-sm md:col-span-2">
      <div className="h-1 bg-gradient-to-r from-primary/80 to-primary/15" />
      <CardHeader className="space-y-4 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Rocket size={18} className="text-primary" />
              Настроить доступ к панели
            </CardTitle>
            <CardDescription>Шаг 1 — способ публикации, шаг 2 — домен и параметры, затем применение</CardDescription>
          </div>
          {selectedModeInfo ? (
            <Badge variant="outline" className="gap-1.5 font-normal">
              <Check size={12} className="text-primary" />
              {selectedModeInfo.title}
            </Badge>
          ) : null}
        </div>
        {previewAccessUrl ? (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
            <span className="text-xs text-muted-foreground">После применения:</span>
            <code className="break-all font-mono text-xs text-primary">{previewAccessUrl}</code>
          </div>
        ) : null}
      </CardHeader>

      <CardContent className="flex min-h-0 flex-1 flex-col space-y-0 pb-0">
        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pb-4">
        <FormSection title="1. Способ публикации" description="Сначала выберите стек, затем конкретный режим сертификата.">
          <div className="flex flex-col gap-2 sm:flex-row">
            {PUBLISH_STACKS.map((stack) => {
              const active = activeStack === stack.id
              return (
                <button
                  key={stack.id}
                  type="button"
                  onClick={() => handleStackChange(stack.id)}
                  className={cn(
                    'flex flex-1 flex-col items-start rounded-xl border px-4 py-3 text-left transition-all',
                    active
                      ? 'border-primary bg-primary/5 ring-1 ring-primary'
                      : 'bg-card/50 hover:border-muted-foreground/30 hover:bg-muted/20',
                  )}
                >
                  <span className="text-sm font-medium">{stack.title}</span>
                  <span className="mt-0.5 text-xs text-muted-foreground">{stack.hint}</span>
                  {stack.id === 'nginx' ? (
                    <Badge variant="success" className="mt-2 gap-1 text-[10px]">
                      <Sparkles size={10} />
                      Рекомендуется
                    </Badge>
                  ) : null}
                </button>
              )
            })}
          </div>

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {visibleModes.map((mode) => {
              const Icon = publishModeIcon(mode.key)
              const methodLabel = publishModeMethodLabel(mode)
              const selected = selectedMode === mode.key
              const recommended = mode.key === 'nginx_le'
              return (
                <button
                  key={mode.key}
                  type="button"
                  onClick={() => onSelectMode(mode.key)}
                  className={cn(
                    'relative flex flex-col gap-2.5 rounded-xl border p-3.5 text-left transition-all',
                    selected
                      ? 'border-primary bg-primary/5 ring-1 ring-primary'
                      : 'bg-card/40 hover:border-muted-foreground/30 hover:bg-muted/20',
                  )}
                >
                  {selected ? (
                    <span className="absolute right-2.5 top-2.5 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground">
                      <Check size={12} strokeWidth={3} />
                    </span>
                  ) : null}
                  <div className="flex items-center gap-2.5">
                    <div
                      className={cn(
                        'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                        selected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground',
                      )}
                    >
                      <Icon size={16} />
                    </div>
                    <div className="min-w-0 pr-6">
                      <p className="text-sm font-medium leading-tight">{mode.title}</p>
                      {methodLabel ? (
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-primary/80">{methodLabel}</p>
                      ) : null}
                    </div>
                  </div>
                  <p className="text-xs leading-relaxed text-muted-foreground">{mode.description}</p>
                  {recommended ? (
                    <Badge variant="success" className="w-fit text-[10px]">
                      По умолчанию
                    </Badge>
                  ) : null}
                </button>
              )
            })}
          </div>
        </FormSection>

        {(showAddressHint || modeWarningLines.length > 0 || showServerUvicornHints) && (
          <FormSection title="Примечания к выбранному режиму">
            <div className="space-y-3">
              {showAddressHint ? (
                <SettingsAlert variant="info" title={addressHint.title}>
                  <p className="text-sm leading-relaxed">{addressHint.lines[0]}</p>
                </SettingsAlert>
              ) : null}
              {modeWarningLines.length > 0 ? (
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
              ) : null}
              {showServerUvicornHints ? (
                <SettingsAlert variant="info" title={publishUvicornWarningsTitle(selectedMode, uvicornWarnings)}>
                  <ul className="list-disc space-y-1 pl-4">
                    {uvicornWarnings.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </SettingsAlert>
              ) : null}
            </div>
          </FormSection>
        )}

        <FormSection
          title="2. Параметры"
          description="Домен, порты и при необходимости подпуть на общем домене."
          className="rounded-xl border bg-muted/15 p-4"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            {(selectedModeInfo?.requires_domain || showOptionalDomain) && (
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="vpn-domain">
                  {selectedModeInfo?.requires_domain
                    ? 'Адрес сайта (домен)'
                    : selfsignedDomainHint
                      ? 'Адрес сайта (домен или IP)'
                      : 'Домен (необязательно)'}
                </Label>
                <Input
                  id="vpn-domain"
                  value={domain}
                  onChange={(e) => onDomainChange(e.target.value)}
                  placeholder={
                    selfsignedDomainHint ? '192.168.1.10' : 'panel.example.com'
                  }
                  className="font-mono"
                />
                {!selectedModeInfo?.requires_domain ? (
                  <p className="text-xs text-muted-foreground">
                    {selfsignedDomainHint
                      ? 'Попадёт в CN самоподписанного сертификата. Без домена — IP сервера.'
                      : 'Для подсказок URL и CORS; если уже в .env — можно оставить пустым'}
                  </p>
                ) : null}
              </div>
            )}

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
                onChange={(e) => onBackendPortChange(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {showUvicornHttpsPort
                  ? 'Uvicorn слушает этот порт с TLS'
                  : 'Обычно 8000 — внутренний порт панели'}
              </p>
              <PortStatusHint status={portStatuses.backend} />
            </div>

            {showLetsEncryptEmail && (
              <div className="space-y-2">
                <Label htmlFor="vpn-email">Email для сертификата</Label>
                <Input
                  id="vpn-email"
                  type="email"
                  value={email}
                  onChange={(e) => onEmailChange(e.target.value)}
                  placeholder="admin@example.com"
                />
                <p className="text-xs text-muted-foreground">Для Let&apos;s Encrypt</p>
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
                    onChange={(e) => onHttpsPublicPortChange(e.target.value)}
                  />
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
                    onChange={(e) => onHttpAcmePortChange(e.target.value)}
                  />
                  <PortStatusHint status={portStatuses.nginx_http} />
                </div>
              </>
            )}
          </div>

          {showAccessPathField ? (
            <div className="mt-4 border-t border-border/60 pt-4">
              <SharedDomainPublishSection
                domain={domain}
                accessPath={accessPath}
                httpsPublicPort={httpsPublicPort}
                previewAccessUrl={previewAccessUrl}
                settings={settings}
                nginxSubpathIntegrate={nginxSubpathIntegrate}
                onAccessPathChange={onAccessPathChange}
                onAccessPathBlur={onAccessPathBlur}
                onIntegrateChange={onIntegrateChange}
                showStatusOpenVpnIntegrate={showStatusOpenVpnIntegrate}
                showGenericSubpathIntegrate={showGenericSubpathIntegrate}
              />
            </div>
          ) : null}

          {showSslPaths ? (
            <div className="mt-4 space-y-4 border-t border-border/60 pt-4">
              <div>
                <p className="text-sm font-medium">Пути к сертификатам</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Абсолютные пути на сервере или выбор из найденных.
                </p>
              </div>
              {(settings.ssl_cert_suggestions?.length ?? 0) > 0 && (
                <div className="flex flex-wrap gap-2">
                  {settings.ssl_cert_suggestions!.map((item) => (
                    <Button
                      key={`${item.source}-${item.cert}`}
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-auto max-w-full whitespace-normal text-left text-xs"
                      onClick={() => onPickSslSuggestion(item.cert, item.key)}
                    >
                      {item.label}
                    </Button>
                  ))}
                </div>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="vpn-ssl-cert">Сертификат (.pem / .crt)</Label>
                  <Input
                    id="vpn-ssl-cert"
                    value={sslCert}
                    onChange={(e) => onSslCertChange(e.target.value)}
                    placeholder="/etc/letsencrypt/live/your-domain/fullchain.pem"
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="vpn-ssl-key">Приватный ключ (.key)</Label>
                  <Input
                    id="vpn-ssl-key"
                    value={sslKey}
                    onChange={(e) => onSslKeyChange(e.target.value)}
                    placeholder="/etc/letsencrypt/live/your-domain/privkey.pem"
                    className="font-mono text-xs"
                  />
                </div>
              </div>
            </div>
          ) : null}
        </FormSection>

        <div className="space-y-3">
          {selectedMode === 'nginx_le' && hasLetsEncryptHint(settings, domain, domainLetsEncrypt) ? (
            <SettingsAlert variant="info" title="Сертификат найден">
              <p className="text-sm leading-relaxed">Let&apos;s Encrypt для домена уже есть — будет переиспользован.</p>
              {foundLetsEncryptPaths ? (
                <p className="mt-1.5 break-all font-mono text-xs text-muted-foreground">{foundLetsEncryptPaths.cert}</p>
              ) : null}
            </SettingsAlert>
          ) : null}
          {showNginxPorts && settings.nginx_installed === false ? (
            <SettingsAlert variant="info" title="Nginx не установлен">
              Nginx будет установлен автоматически. Убедитесь, что порты 80/443 открыты.
            </SettingsAlert>
          ) : null}
          {selectedMode === 'http_direct' && previewAccessUrl ? (
            <SettingsAlert variant="warning" title="Только HTTP">
              Домен из настроек не используется — панель откроется по IP-адресу сервера.
            </SettingsAlert>
          ) : null}
        </div>
        </div>

        <div className="sticky bottom-0 -mx-6 flex shrink-0 flex-col gap-3 border-t bg-card/95 px-6 py-4 pb-safe backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 space-y-0.5">
            <p className="text-xs font-medium text-muted-foreground">Готово к применению</p>
            {previewAccessUrl ? (
              <a
                href={previewAccessUrl}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 break-all font-mono text-xs text-primary hover:underline"
              >
                {previewAccessUrl}
                <ExternalLink size={12} className="shrink-0" />
              </a>
            ) : (
              <p className="text-xs text-muted-foreground">Укажите домен или параметры для preview URL</p>
            )}
          </div>
          <Button onClick={onPublish} disabled={publishing} className="shrink-0 gap-1.5" size="lg">
            <Rocket size={18} className={publishing ? 'animate-pulse' : ''} />
            {publishing ? 'Применение…' : 'Применить настройки'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
