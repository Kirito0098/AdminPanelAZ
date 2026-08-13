import { Layers, Server } from 'lucide-react'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  PROXY_LINK_NONE,
  proxyLinkSelectorOptions,
} from '@/lib/proxyLinkTarget'
import type { Node, NodeSyncGroup } from '@/types'

type ProxyLinkSelectProps = {
  id?: string
  value: string
  onChange: (value: string) => void
  nodes: Node[]
  syncGroups: NodeSyncGroup[]
  disabled?: boolean
  /** Extra SelectItem when linked node is missing from options */
  orphanNodeId?: number | null
}

export default function ProxyLinkSelect({
  id = 'proxy-link-target',
  value,
  onChange,
  nodes,
  syncGroups,
  disabled = false,
  orphanNodeId = null,
}: ProxyLinkSelectProps) {
  const options = proxyLinkSelectorOptions(nodes, syncGroups)
  const groups = options.filter((o) => o.type === 'group')
  const standalones = options.filter((o) => o.type === 'node')
  const showOrphan =
    orphanNodeId != null &&
    value === `node:${orphanNodeId}` &&
    !options.some((o) => o.type === 'node' && o.nodeId === orphanNodeId) &&
    !options.some((o) => o.type === 'group' && o.primaryNodeId === orphanNodeId)

  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>Привязан к</Label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id}>
          <SelectValue placeholder="Не привязан" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={PROXY_LINK_NONE}>Не привязан</SelectItem>
          {groups.length > 0 && (
            <SelectGroup>
              <SelectLabel>HA-группы</SelectLabel>
              {groups.map((option) =>
                option.type === 'group' ? (
                  <SelectItem key={option.key} value={option.key}>
                    <span className="flex items-center gap-2">
                      <Layers size={12} className="shrink-0 text-muted-foreground" />
                      <span className="truncate">{option.label}</span>
                      <span className="truncate text-[10px] text-muted-foreground">
                        {option.sharedDomain}
                      </span>
                    </span>
                  </SelectItem>
                ) : null,
              )}
            </SelectGroup>
          )}
          {standalones.length > 0 && (
            <SelectGroup>
              <SelectLabel>Отдельные серверы</SelectLabel>
              {standalones.map((option) =>
                option.type === 'node' ? (
                  <SelectItem key={option.key} value={option.key}>
                    <span className="flex items-center gap-2">
                      <Server size={12} className="shrink-0 text-muted-foreground" />
                      <span className="truncate">{option.label}</span>
                    </span>
                  </SelectItem>
                ) : null,
              )}
            </SelectGroup>
          )}
          {showOrphan && orphanNodeId != null && (
            <SelectItem value={`node:${orphanNodeId}`}>
              узел #{orphanNodeId} (не найден)
            </SelectItem>
          )}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground">
        Чтобы при нескольких прокси было ясно, к какой HA-группе или VPN-серверу относится этот
        прокси. На DESTINATION и трафик не влияет.
      </p>
    </div>
  )
}
