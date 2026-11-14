import {
  Download,
  HeartPulse,
  KeyRound,
  Loader2,
  Pencil,
  Power,
  RefreshCw,
  Server,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Node, NodeTransportId } from '@/types'
import NodeTransportSelect from './NodeTransportSelect'

type NodeActionsProps = {
  node: Node
  isActive: boolean
  isProxy: boolean
  healthLoading: boolean
  activateLoading: boolean
  onActivate: () => void
  onHealth: () => void
  onUpdate: () => void
  onRestart: () => void
  onRotateKey: () => void
  onTransportChange: (transport: NodeTransportId) => void
  onEdit: () => void
  onDelete: () => void
  /** Stage 4: выдать сервер пользователям (показывается только для доступных серверов). */
  onAssignToUsers?: () => void
  compact?: boolean
}

export default function NodeActions({
  node,
  isActive,
  isProxy,
  healthLoading,
  activateLoading,
  onActivate,
  onHealth,
  onUpdate,
  onRestart,
  onRotateKey,
  onTransportChange,
  onEdit,
  onDelete,
  onAssignToUsers,
  compact = false,
}: NodeActionsProps) {
  const btnSize = compact ? 'icon' : 'sm'
  const iconSize = compact ? 16 : 14

  return (
    <div className={cn('flex flex-wrap items-center', compact ? 'justify-end gap-0.5' : 'gap-2')}>
      {!isProxy && !isActive && (
        <Button
          variant={compact ? 'ghost' : 'outline'}
          size={btnSize}
          title="Активировать узел"
          disabled={activateLoading}
          onClick={onActivate}
        >
          {activateLoading ? (
            <Loader2 size={iconSize} className="animate-spin" />
          ) : (
            <Power size={iconSize} />
          )}
          {!compact && 'Активировать'}
        </Button>
      )}
      <Button
        variant={compact ? 'ghost' : 'outline'}
        size={btnSize}
        title="Проверить связь"
        disabled={healthLoading}
        onClick={onHealth}
      >
        {healthLoading ? (
          <Loader2 size={iconSize} className="animate-spin" />
        ) : (
          <HeartPulse size={iconSize} />
        )}
        {!compact && 'Здоровье'}
      </Button>
      {!isProxy && (
        <Button
          variant={compact ? 'ghost' : 'outline'}
          size={btnSize}
          title="Обновление узла"
          onClick={onUpdate}
        >
          <Download size={iconSize} />
          {!compact && 'Обновить'}
        </Button>
      )}
      {!isProxy && (
        <Button
          variant={compact ? 'ghost' : 'outline'}
          size={btnSize}
          title="Перезапуск node agent"
          onClick={onRestart}
        >
          <RefreshCw size={iconSize} />
          {!compact && 'Перезапуск'}
        </Button>
      )}
      {!node.is_local && (
        <>
          <NodeTransportSelect
            node={node}
            compact={compact}
            onChange={onTransportChange}
          />
          {!isProxy && (
            <Button
              variant={compact ? 'ghost' : 'outline'}
              size={btnSize}
              title="Ротация API-ключа"
              onClick={onRotateKey}
            >
              <KeyRound size={iconSize} />
              {!compact && 'Ключ'}
            </Button>
          )}
        </>
      )}
      {onAssignToUsers && (
        <Button
          variant={compact ? 'ghost' : 'outline'}
          size={btnSize}
          title="Выдать этот сервер пользователям"
          onClick={onAssignToUsers}
        >
          <Server size={iconSize} />
          {!compact && 'Выдать пользователям'}
        </Button>
      )}
      <Button
        variant={compact ? 'ghost' : 'outline'}
        size={btnSize}
        title={node.is_local ? 'Переименовать' : 'Редактировать'}
        onClick={onEdit}
      >
        <Pencil size={iconSize} />
        {!compact && (node.is_local ? 'Имя' : 'Изменить')}
      </Button>
      {!node.is_local && (
        <Button
          variant={compact ? 'ghost' : 'outline'}
          size={btnSize}
          title="Удалить"
          className="text-destructive hover:text-destructive"
          onClick={onDelete}
        >
          <Trash2 size={iconSize} />
          {!compact && 'Удалить'}
        </Button>
      )}
    </div>
  )
}
