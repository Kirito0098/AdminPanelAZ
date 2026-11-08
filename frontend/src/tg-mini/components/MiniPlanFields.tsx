import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { TgMiniNode } from '@/types'

const PROTOCOL_OPTIONS = ['openvpn', 'wireguard', 'amneziawg2'] as const

interface MiniPlanFieldsProps {
  nodes: TgMiniNode[]
  nodeIds: number[]
  onNodeIdsChange: (ids: number[]) => void
  protocols: string[]
  onProtocolsChange: (protocols: string[]) => void
  count: string
  onCountChange: (count: string) => void
  idPrefix: string
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
}

/** Общие поля плана конфигов: узлы, протоколы, число имён. */
export default function MiniPlanFields({
  nodes,
  nodeIds,
  onNodeIdsChange,
  protocols,
  onProtocolsChange,
  count,
  onCountChange,
  idPrefix,
}: MiniPlanFieldsProps) {
  return (
    <>
      <div className="space-y-1.5">
        <Label>Узлы</Label>
        <div className="flex flex-wrap gap-1.5">
          {nodes.map((node) => (
            <button
              key={node.id}
              type="button"
              className={cn(
                'rounded-md border px-2 py-1 text-xs',
                nodeIds.includes(node.id) ? 'border-primary bg-primary/10' : 'border-border',
              )}
              onClick={() => onNodeIdsChange(toggle(nodeIds, node.id))}
            >
              {node.name}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>Протоколы</Label>
        <div className="flex flex-wrap gap-1.5">
          {PROTOCOL_OPTIONS.map((protocol) => (
            <button
              key={protocol}
              type="button"
              className={cn(
                'rounded-md border px-2 py-1 text-xs',
                protocols.includes(protocol) ? 'border-primary bg-primary/10' : 'border-border',
              )}
              onClick={() => onProtocolsChange(toggle(protocols, protocol))}
            >
              {protocol}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-count`}>Имён конфигов</Label>
        <Input
          id={`${idPrefix}-count`}
          inputMode="numeric"
          value={count}
          onChange={(e) => onCountChange(e.target.value)}
        />
      </div>
    </>
  )
}
