import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export type ProtocolFilter = 'all' | 'openvpn' | 'wireguard'

type ProtocolCounts = Partial<Record<ProtocolFilter, number>>

interface MiniListToolbarProps {
  search: string
  onSearchChange: (value: string) => void
  searchPlaceholder?: string
  protocol?: ProtocolFilter
  onProtocolChange?: (value: ProtocolFilter) => void
  protocolCounts?: ProtocolCounts
  className?: string
}

const PROTOCOL_OPTIONS: Array<{ value: ProtocolFilter; label: string }> = [
  { value: 'all', label: 'Все' },
  { value: 'openvpn', label: 'OpenVPN' },
  { value: 'wireguard', label: 'WG / AWG' },
]

export function matchesSearchQuery(value: string, query: string): boolean {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  return value.toLowerCase().includes(normalized)
}

export function matchesProtocolFilter(vpnType: string, filter: ProtocolFilter): boolean {
  if (filter === 'all') return true
  return vpnType === filter
}

export default function MiniListToolbar({
  search,
  onSearchChange,
  searchPlaceholder = 'Поиск…',
  protocol,
  onProtocolChange,
  protocolCounts,
  className,
}: MiniListToolbarProps) {
  const showProtocol = protocol != null && onProtocolChange != null

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

      {showProtocol && (
        <div className="tg-mini-segmented" role="tablist" aria-label="Фильтр протокола">
          {PROTOCOL_OPTIONS.map((option) => {
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
