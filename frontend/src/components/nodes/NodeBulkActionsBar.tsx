import {
  Download,
  HeartPulse,
  Loader2,
  MoreHorizontal,
  Shield,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { Node } from '@/types'
import { getSelectedNodes } from './nodeHelpers'
import { isProxyNode } from './nodeKind'

export type NodeBulkActionsBarProps = {
  nodes: Node[]
  selectedNodeIds: number[]
  bulkBusy: boolean
  rollingUpdating: boolean
  rollPolling: boolean
  onSelectAll: () => void
  onClearSelection: () => void
  onBulkHealth: () => void
  onBulkRollingUpdate: () => void
  onBulkEnableMtls: () => void
  onBulkDelete: () => void
}

export default function NodeBulkActionsBar({
  nodes,
  selectedNodeIds,
  bulkBusy,
  rollingUpdating,
  rollPolling,
  onSelectAll,
  onClearSelection,
  onBulkHealth,
  onBulkRollingUpdate,
  onBulkEnableMtls,
  onBulkDelete,
}: NodeBulkActionsBarProps) {
  const selected = getSelectedNodes(nodes, selectedNodeIds)
  const remoteSelected = selected.filter((node) => !node.is_local)
  const mtlsCandidates = remoteSelected.filter(
    (node) => !isProxyNode(node) && !node.mtls_enabled,
  )
  const allSelected = nodes.length > 0 && selectedNodeIds.length === nodes.length
  const busy = bulkBusy || rollingUpdating || rollPolling

  if (nodes.length === 0) return null

  return (
    <div className="mb-4 rounded-md border bg-muted/30 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">
          Выбрано: {selectedNodeIds.length} из {nodes.length}
        </span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          disabled={busy || allSelected}
          onClick={onSelectAll}
        >
          Выбрать все
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          disabled={busy || selectedNodeIds.length === 0}
          onClick={onClearSelection}
        >
          Сброс
        </Button>
        <div className="hidden h-5 w-px bg-border md:block" />
        <div className="hidden flex-wrap items-center gap-2 md:flex">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={busy || selectedNodeIds.length === 0}
            onClick={onBulkHealth}
          >
            <HeartPulse size={12} />
            Проверить здоровье
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={busy || selectedNodeIds.length === 0}
            onClick={onBulkRollingUpdate}
          >
            {rollingUpdating || rollPolling ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Download size={12} />
            )}
            Rolling update
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={busy || mtlsCandidates.length === 0}
            onClick={onBulkEnableMtls}
            title={
              mtlsCandidates.length === 0 && remoteSelected.length > 0
                ? 'У выбранных удалённых узлов mTLS уже включён'
                : undefined
            }
          >
            <Shield size={12} />
            Включить mTLS{mtlsCandidates.length > 0 ? ` (${mtlsCandidates.length})` : ''}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="destructive"
            className="h-7 text-xs"
            disabled={busy || remoteSelected.length === 0}
            onClick={onBulkDelete}
          >
            <Trash2 size={12} />
            Удалить{remoteSelected.length > 0 ? ` (${remoteSelected.length})` : ''}
          </Button>
        </div>
        <div className="md:hidden">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={busy || selectedNodeIds.length === 0}
              >
                <MoreHorizontal size={12} />
                Действия с выбранными
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuItem disabled={busy || selectedNodeIds.length === 0} onClick={onBulkHealth}>
                <HeartPulse size={14} />
                Проверить здоровье
              </DropdownMenuItem>
              <DropdownMenuItem disabled={busy || selectedNodeIds.length === 0} onClick={onBulkRollingUpdate}>
                <Download size={14} />
                Rolling update
              </DropdownMenuItem>
              <DropdownMenuItem disabled={busy || mtlsCandidates.length === 0} onClick={onBulkEnableMtls}>
                <Shield size={14} />
                Включить mTLS{mtlsCandidates.length > 0 ? ` (${mtlsCandidates.length})` : ''}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                disabled={busy || remoteSelected.length === 0}
                onClick={onBulkDelete}
              >
                <Trash2 size={14} />
                Удалить{remoteSelected.length > 0 ? ` (${remoteSelected.length})` : ''}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  )
}
