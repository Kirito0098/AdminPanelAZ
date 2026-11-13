import { cn } from '@/lib/utils'
import { protocolBadgeClass, protocolLabel } from '@/lib/vpnTypes'

interface ProtocolBadgeProps {
  protocol: string
  className?: string
}

/** Единый бейдж протокола: одна подпись и цвета на всех экранах панели и Mini App. */
export function ProtocolBadge({ protocol, className }: ProtocolBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-none',
        protocolBadgeClass(protocol),
        className,
      )}
    >
      {protocolLabel(protocol)}
    </span>
  )
}
