import { Copy } from 'lucide-react'
import type { ClientAccessPolicy, VpnConfig } from '@/types'
import {
  buildAccessMeta,
  hasAzProfiles,
  hasVpnProfiles,
  protocolLabel,
  type ProtocolTab,
} from '@/lib/configCardUtils'
import { cn } from '@/lib/utils'

interface ConfigCardProps {
  config: VpnConfig
  tab: ProtocolTab
  policy?: ClientAccessPolicy
  onOpen: () => void
  onCopyName: () => void
}

export default function ConfigCard({ config, tab, policy, onOpen, onCopyName }: ConfigCardProps) {
  const isBlocked = policy?.is_blocked ?? false
  const { lines, tone } = buildAccessMeta(config, tab, policy)
  const showMeta = Boolean(policy) || config.vpn_type === 'openvpn'

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
      className={cn(
        'group flex w-full cursor-pointer flex-col items-start gap-0.5 rounded-lg border px-2.5 py-2 text-left',
        'border-primary/45 bg-gradient-to-br from-background/95 to-muted/40',
        'shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_4px_14px_rgba(0,0,0,0.28)]',
        'transition-all duration-200 hover:-translate-y-px hover:border-primary/70',
        'hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_12px_28px_rgba(0,0,0,0.35),0_0_0_1px_rgba(120,200,140,0.24)]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
      )}
    >
      <div className="flex w-full items-start justify-between gap-1">
        <span className="truncate text-[0.91rem] font-bold leading-tight text-foreground">{config.client_name}</span>
        <button
          type="button"
          title="Копировать имя"
          onClick={(e) => {
            e.stopPropagation()
            onCopyName()
          }}
          className="shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-primary group-hover:opacity-100"
        >
          <Copy size={12} />
        </button>
      </div>

      <span
        className={cn(
          'inline-flex items-center rounded-full border px-1.5 py-0.5 text-[0.68rem] font-bold leading-tight',
          isBlocked
            ? 'border-destructive/50 bg-destructive/20 text-red-200'
            : 'border-primary/40 bg-primary/15 text-emerald-200',
        )}
      >
        {isBlocked ? 'Заблокирован' : 'Активный'}
      </span>

      {showMeta && (
        <div
          className={cn(
            'mt-0.5 space-y-0.5 text-[0.72rem] leading-snug',
            tone === 'expired' && 'text-destructive/90',
            tone === 'expiring' && 'text-amber-400/90',
            tone === 'active' && 'text-muted-foreground',
          )}
        >
          {lines.map((line) => (
            <div key={line.text}>{line.text}</div>
          ))}
        </div>
      )}

      <div className="mt-1 flex flex-wrap gap-1">
        <span className="inline-flex items-center rounded-full border border-sky-500/40 bg-sky-500/20 px-1.5 py-0.5 text-[0.66rem] font-bold text-sky-200">
          {protocolLabel(tab)}
        </span>
        {hasVpnProfiles(config) && (
          <span className="inline-flex items-center rounded-full border border-primary/35 bg-primary/15 px-1.5 py-0.5 text-[0.66rem] font-bold text-emerald-200">
            VPN
          </span>
        )}
        {hasAzProfiles(config) && (
          <span className="inline-flex items-center rounded-full border border-amber-500/45 bg-amber-500/20 px-1.5 py-0.5 text-[0.66rem] font-bold text-amber-200">
            AZ
          </span>
        )}
      </div>

      <span className="mt-1 text-[0.67rem] text-muted-foreground/80">
        {tab === 'openvpn' ? 'Открыть действия и график' : 'Нажмите для действий'}
      </span>
    </div>
  )
}
