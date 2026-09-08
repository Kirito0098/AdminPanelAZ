import {
  Download,
  HeartPulse,
  KeyRound,
  Loader2,
  Pencil,
  Power,
  RefreshCw,
  Shield,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Node } from '@/types'

export type NodeActionsProps = {
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
  onEnableMtls: () => void
  onDisableMtls: () => void
  onEdit: () => void
  onDelete: () => void
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
  onEnableMtls,
  onDisableMtls,
  onEdit,
  onDelete,
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
        title="Проверка здоровья"
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
          {!node.mtls_enabled && (
            <Button
              variant={compact ? 'ghost' : 'outline'}
              size={btnSize}
              title={isProxy ? 'Отметить mTLS (сертификаты вручную)' : 'Включить mTLS'}
              onClick={onEnableMtls}
            >
              <Shield size={iconSize} />
              {!compact && (isProxy ? 'Отметить mTLS' : 'Включить mTLS')}
            </Button>
          )}
          {node.mtls_enabled && (
            <Button
              variant={compact ? 'ghost' : 'outline'}
              size={btnSize}
              title="Сбросить флаг mTLS в панели"
              onClick={onDisableMtls}
            >
              <Shield size={iconSize} />
              {!compact && 'Отключить mTLS'}
            </Button>
          )}
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
          <Button
            variant={compact ? 'ghost' : 'outline'}
            size={btnSize}
            title="Редактировать"
            onClick={onEdit}
          >
            <Pencil size={iconSize} />
            {!compact && 'Изменить'}
          </Button>
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
        </>
      )}
    </div>
  )
}
