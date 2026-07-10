import { Activity, ArrowRight, ExternalLink, Globe, Link2, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { formatPublicHttpsOrigin } from '@/components/settings/publishWizardUi'
import type { VpnNetworkSettings } from '@/types'

type SharedDomainPublishSectionProps = {
  domain: string
  accessPath: string
  httpsPublicPort: string
  previewAccessUrl?: string
  settings: VpnNetworkSettings
  nginxSubpathIntegrate: boolean
  onAccessPathChange: (value: string) => void
  onAccessPathBlur: () => void
  onIntegrateChange: (checked: boolean) => void
  showStatusOpenVpnIntegrate: boolean
  showGenericSubpathIntegrate: boolean
}

function domainHost(domain: string): string {
  return domain.trim().split(':')[0]
}

function pathSegment(accessPath: string): string {
  return accessPath.trim().replace(/^\/+|\/+$/g, '')
}

function PathCoexistenceRow({
  path,
  label,
  tone,
}: {
  path: string
  label: string
  tone: 'status' | 'panel'
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-lg border px-3 py-2',
        tone === 'status' && 'border-sky-500/25 bg-sky-500/5',
        tone === 'panel' && 'border-primary/25 bg-primary/5',
      )}
    >
      <code className="min-w-0 flex-1 truncate font-mono text-xs">{path}</code>
      <ArrowRight size={14} className="shrink-0 text-muted-foreground" />
      <span className="shrink-0 text-xs font-medium text-muted-foreground">{label}</span>
    </div>
  )
}

function IntegrateToggleRow({
  id,
  title,
  description,
  checked,
  onCheckedChange,
  highlighted,
}: {
  id: string
  title: ReactNode
  description: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  highlighted?: boolean
}) {
  return (
    <div
      className={cn(
        'flex items-start justify-between gap-4 rounded-xl border p-4 transition-colors',
        checked && highlighted ? 'border-primary/30 bg-primary/5' : 'border-border/60 bg-card/40',
      )}
    >
      <div className="min-w-0 space-y-1.5">
        <Label htmlFor={id} className="cursor-pointer text-sm font-medium leading-snug">
          {title}
        </Label>
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} className="mt-0.5" />
    </div>
  )
}

export default function SharedDomainPublishSection({
  domain,
  accessPath,
  httpsPublicPort,
  previewAccessUrl,
  settings,
  nginxSubpathIntegrate,
  onAccessPathChange,
  onAccessPathBlur,
  onIntegrateChange,
  showStatusOpenVpnIntegrate,
  showGenericSubpathIntegrate,
}: SharedDomainPublishSectionProps) {
  const host = domainHost(domain)
  const segment = pathSegment(accessPath)
  const hasPath = Boolean(segment)
  const origin = host ? formatPublicHttpsOrigin(host, httpsPublicPort) : 'https://ваш-домен'

  return (
    <div className="space-y-4 rounded-xl border border-primary/20 bg-gradient-to-br from-primary/5 via-card/50 to-card p-4 sm:col-span-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
            <Globe size={18} />
          </div>
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-semibold">Общий домен</p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Разместите панель по подпути рядом с другими проектами на том же домене.
            </p>
          </div>
        </div>
        {settings.shared_domain_status_openvpn && (
          <Badge variant="secondary" className="gap-1 border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300">
            <Activity size={12} />
            StatusOpenVPN обнаружен
          </Badge>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="vpn-access-path">Подпуть панели</Label>
        <div
          className={cn(
            'flex h-10 items-stretch overflow-hidden rounded-lg border border-input bg-background shadow-sm',
            'transition-shadow focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background',
            !host && 'opacity-80',
          )}
        >
          <div className="flex max-w-[min(100%,14rem)] shrink-0 items-center gap-0 border-r border-border/60 bg-muted/20 px-3 sm:max-w-none">
            <span className="truncate font-mono text-xs text-muted-foreground" title={origin}>
              {origin}
            </span>
            <span className="font-mono text-xs text-muted-foreground/60">/</span>
          </div>
          <input
            id="vpn-access-path"
            type="text"
            inputMode="text"
            autoComplete="off"
            spellCheck={false}
            value={segment}
            onChange={(e) => onAccessPathChange(e.target.value ? `/${pathSegment(e.target.value)}` : '')}
            onBlur={onAccessPathBlur}
            placeholder={host ? 'panel' : 'укажите домен выше'}
            disabled={!host}
            className="min-w-0 flex-1 bg-transparent px-3 font-mono text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
          />
        </div>
        {host && hasPath && previewAccessUrl ? (
          <p className="text-xs text-muted-foreground">
            Полный адрес:{' '}
            <code className="break-all font-mono text-primary">{previewAccessUrl}</code>
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">
            {host
              ? 'Оставьте пустым для корня домена. Подпуть — дополнительная мера, не замена 2FA.'
              : 'Сначала укажите домен в поле «Адрес сайта» — тогда можно задать подпуть.'}
          </p>
        )}
      </div>

      {settings.shared_domain_status_openvpn && hasPath && host && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">На домене будут работать параллельно</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <PathCoexistenceRow path={`${origin}/status/`} label="StatusOpenVPN" tone="status" />
            <PathCoexistenceRow
              path={`${origin}/${segment}/`}
              label="AdminPanelAZ"
              tone="panel"
            />
          </div>
        </div>
      )}

      {showStatusOpenVpnIntegrate && (
        <IntegrateToggleRow
          id="vpn-status-openvpn-integrate"
          highlighted
          checked={nginxSubpathIntegrate}
          onCheckedChange={onIntegrateChange}
          title={
            <span className="inline-flex flex-wrap items-center gap-1.5">
              Интегрировать с{' '}
              <a
                href="https://github.com/TheMurmabis/StatusOpenVPN"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
              >
                StatusOpenVPN
                <ExternalLink size={12} />
              </a>
            </span>
          }
          description="Добавит include только в sites-enabled, не трогая /status/. Перед изменением создаётся бэкап nginx-конфига."
        />
      )}

      {showGenericSubpathIntegrate && (
        <IntegrateToggleRow
          id="vpn-subpath-integrate"
          checked={nginxSubpathIntegrate}
          onCheckedChange={onIntegrateChange}
          title={
            <span className="inline-flex items-center gap-1.5">
              <Link2 size={14} />
              Встроить в существующий nginx vhost
            </span>
          }
          description="Автоматически добавит include snippet в vhost домена. Перед правкой создаётся бэкап конфига."
        />
      )}

      {showStatusOpenVpnIntegrate && hasPath && !nginxSubpathIntegrate && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-muted-foreground">
          <ShieldCheck size={14} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
          <span>
            Интеграция выключена — snippet будет создан, но include в nginx нужно будет добавить вручную.
          </span>
        </div>
      )}
    </div>
  )
}
