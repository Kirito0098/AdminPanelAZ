import { useEffect, useState } from 'react'
import { listNodeTransports } from '@/api/nodes'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import type { Node, NodeTransportId, NodeTransportOption } from '@/types'

const DEFAULT_ITEMS: NodeTransportOption[] = [
  { id: 'http', label: 'HTTP', available: true },
  { id: 'mtls', label: 'HTTPS + mTLS', available: true },
  { id: 'ssh', label: 'SSH tunnel', available: false },
]

function resolveTransport(node: Node): NodeTransportId {
  const raw = (node.transport || (node.mtls_enabled ? 'mtls' : 'http')).toLowerCase()
  if (raw === 'mtls' || raw === 'ssh') return raw
  return 'http'
}

export type NodeTransportSelectProps = {
  node: Node
  compact?: boolean
  disabled?: boolean
  onChange: (transport: NodeTransportId) => void
}

export default function NodeTransportSelect({
  node,
  compact = false,
  disabled = false,
  onChange,
}: NodeTransportSelectProps) {
  const [items, setItems] = useState<NodeTransportOption[]>(DEFAULT_ITEMS)
  const current = resolveTransport(node)
  const currentFallback = DEFAULT_ITEMS.find((item) => item.id === current)
  const allItems = items.some((item) => item.id === current) || !currentFallback ? items : [...items, currentFallback]
  const visibleItems = allItems.filter((item) => item.available || item.id === current)

  useEffect(() => {
    let cancelled = false
    listNodeTransports()
      .then((res) => {
        if (!cancelled && Array.isArray(res.items) && res.items.length > 0) {
          setItems(res.items)
        }
      })
      .catch(() => {
        /* keep defaults */
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <Select
      value={current}
      disabled={disabled || node.is_local}
      onValueChange={(value) => {
        const next = value as NodeTransportId
        const opt = items.find((i) => i.id === next)
        if (!opt?.available || next === current) return
        onChange(next)
      }}
    >
      <SelectTrigger
        className={cn(compact ? 'h-8 w-[8.5rem] text-xs' : 'h-9 w-[11rem] text-sm')}
        title="Способ связи"
        aria-label="Способ связи"
      >
        <SelectValue placeholder="Способ связи" />
      </SelectTrigger>
      <SelectContent>
        {visibleItems.map((item) => (
          <SelectItem
            key={item.id}
            value={item.id}
            disabled={!item.available}
            title={item.available ? item.label : 'Модуль отключён'}
          >
            {item.label}
            {!item.available ? ' (выключено)' : ''}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
