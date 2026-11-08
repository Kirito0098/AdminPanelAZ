import { useCallback, useEffect, useState } from 'react'
import { Loader2, Server } from 'lucide-react'
import { ApiError } from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { activateTgNode, getTgNodes } from '@/tg-mini/api'
import type { TgMiniNode } from '@/types'

interface MiniNodeSelectorProps {
  /** Called after the active node actually changed, so the page can reload its data. */
  onChanged?: () => void
}

function nodeCaption(node: TgMiniNode): string {
  const parts = [node.name]
  if (node.ha_role === 'primary') parts.push('основной')
  if (node.ha_role === 'replica') parts.push('реплика')
  if (node.status === 'offline') parts.push('офлайн')
  if (node.node_kind === 'proxy') parts.push('прокси')
  return parts.join(' · ')
}

function isSelectable(node: TgMiniNode): boolean {
  return node.ha_role !== 'replica' && (node.node_kind || 'vpn') !== 'proxy'
}

/** Compact active-node switcher for admin pages (replaces the old «Узлы» tab). */
export default function MiniNodeSelector({ onChanged }: MiniNodeSelectorProps) {
  const [nodes, setNodes] = useState<TgMiniNode[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await getTgNodes()
      setNodes(data.nodes)
      setActiveId(data.active_node_id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось загрузить узлы')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const change = async (value: string) => {
    const nextId = Number(value)
    if (!nextId || nextId === activeId) return
    setBusy(true)
    setError(null)
    try {
      const result = await activateTgNode(nextId)
      setActiveId(result.node.id)
      await load()
      onChanged?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка переключения узла')
    } finally {
      setBusy(false)
    }
  }

  if (nodes.length === 0) return null

  return (
    <Card>
      <CardContent className="space-y-1.5 p-3">
        <div className="flex items-center gap-2">
          <Server size={16} className="shrink-0 text-muted-foreground" aria-hidden />
          <span className="text-xs font-medium text-muted-foreground">Активный сервер</span>
          <select
            value={activeId ?? ''}
            onChange={(e) => void change(e.target.value)}
            disabled={busy}
            aria-label="Активный сервер"
            className="ml-auto min-w-0 max-w-[65%] rounded-md border border-input bg-background px-2 py-1 text-sm"
          >
            {activeId == null && <option value="">—</option>}
            {nodes.map((node) => (
              <option key={node.id} value={node.id} disabled={!isSelectable(node)}>
                {nodeCaption(node)}
              </option>
            ))}
          </select>
          {busy && <Loader2 size={14} className="animate-spin text-muted-foreground" aria-hidden />}
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
