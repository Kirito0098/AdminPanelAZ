import { Link } from 'react-router-dom'
import { CloudOff, Server } from 'lucide-react'
import EmptyState from '@/components/ui/EmptyState'
import { Button } from '@/components/ui/button'
import type { Node, WarperHealthResponse } from '@/types'
import { INSTALL_CMD, formatNodeLabel } from './utils'

interface WarperInstallPromptProps {
  health: WarperHealthResponse | null
  activeNode: Node | null
}

export default function WarperInstallPrompt({ health, activeNode }: WarperInstallPromptProps) {
  const nodeLabel = formatNodeLabel(health, activeNode)

  return (
    <div className="rounded-xl border bg-card/50 p-6">
      <EmptyState
        icon={CloudOff}
        title="Управление недоступно"
        description={`На узле ${nodeLabel} AZ-WARP не установлен. Вкладки доменов, подсетей и настроек появятся после установки или переключения на другой узел.`}
      />
      <div className="mx-auto mt-2 max-w-xl space-y-3">
        <div className="flex items-start gap-2 rounded-lg border bg-muted/30 p-3 text-sm">
          <Server className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <p className="text-muted-foreground">
            Уже установили на другом VPN-сервере? Выберите его в селекторе узла справа вверху.
          </p>
        </div>
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Установка на текущем узле (root):</p>
          <pre className="overflow-x-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs">{INSTALL_CMD}</pre>
        </div>
        <div className="flex justify-center pt-1">
          <Button variant="outline" size="sm" asChild>
            <Link to="/nodes">Перейти к узлам</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
