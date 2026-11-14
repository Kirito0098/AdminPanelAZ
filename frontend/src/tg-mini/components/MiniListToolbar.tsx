import type { CSSProperties } from 'react'
import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { PROTOCOL_ORDER, protocolKey, protocolLabel, type Protocol } from '@/lib/vpnTypes'
import { cn } from '@/lib/utils'

export type ProtocolFilter = 'all' | Protocol

type ProtocolCounts = Partial<Record<ProtocolFilter, number>>

interface MiniListToolbarProps {
  search: string
  onSearchChange: (value: string) => void
  searchPlaceholder?: string
  protocol?: ProtocolFilter
  onProtocolChange?: (value: ProtocolFilter) => void
  protocolCounts?: ProtocolCounts
  /** When set, only these protocol chips are shown (plus any implied by counts). */
  protocolOptions?: ProtocolFilter[]
  className?: string
}

const PROTOCOL_OPTIONS: Array<{ value: ProtocolFilter; label: string }> = [
  { value: 'all', label: 'Все' },
  ...PROTOCOL_ORDER.map((protocol) => ({ value: protocol, label: protocolLabel(protocol) })),
]

export function matchesSearchQuery(value: string, query: string): boolean {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  return value.toLowerCase().includes(normalized)
}

export function matchesProtocolFilter(vpnType: string, filter: ProtocolFilter): boolean {
  if (filter === 'all') return true
  const key = protocolKey(vpnType)
  // AmneziaWG 1.5 — та же категория WG/AWG 1.5, что и WireGuard.
  return key === filter || (filter === 'wireguard' && key === 'amneziawg')
}

export default function MiniListToolbar({
  search,
  onSearchChange,
  searchPlaceholder = 'Поиск…',
  protocol,
  onProtocolChange,
  protocolCounts,
  protocolOptions,
  className,
}: MiniListToolbarProps) {
  const showProtocol = protocol != null && onProtocolChange != null
  const options =
    protocolOptions != null
      ? PROTOCOL_OPTIONS.filter((option) => protocolOptions.includes(option.value))
      : PROTOCOL_OPTIONS

  return (
    <div className={cn('tg-mini-list-toolbar', className)}>
      <div className="tg-mini-search-wrap">
        <Search size={15} className="tg-mini-search-icon" aria-hidden />
        <Input
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={searchPlaceholder}
          className="tg-mini-search-input"
          aria-label={searchPlaceholder}
        />
        {search && (
          <button
            type="button"
            className="tg-mini-search-clear"
            onClick={() => onSearchChange('')}
            aria-label="Очистить поиск"
          >
            <X size={14} aria-hidden />
          </button>
        )}
      </div>

      {showProtocol && options.length > 1 && (
        <div
          className="tg-mini-segmented"
          role="tablist"
          aria-label="Фильтр протокола"
          data-cols={options.length}
          style={{ '--tg-mini-segment-cols': options.length } as CSSProperties}
        >
          {options.map((option) => {
            const count = protocolCounts?.[option.value]
            const active = protocol === option.value
            return (
              <button
                key={option.value}
                type="button"
                role="tab"
                aria-selected={active}
                className={cn('tg-mini-segment', active && 'is-active')}
                onClick={() => onProtocolChange(option.value)}
              >
                <span>{option.label}</span>
                {count != null && <span className="tg-mini-segment-count">{count}</span>}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
