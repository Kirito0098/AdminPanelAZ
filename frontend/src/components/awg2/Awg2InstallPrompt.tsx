import { Link } from 'react-router-dom'
import { CloudOff, Server } from 'lucide-react'
import EmptyState from '@/components/ui/EmptyState'
import { Button } from '@/components/ui/button'
import type { Awg2HealthResponse, Node } from '@/types'
import Awg2InstallDialog from './Awg2InstallDialog'
import { AWG2_INSTALL_CMD, formatAwg2NodeLabel } from './utils'

interface Awg2InstallPromptProps {
  health: Awg2HealthResponse | null
  activeNode: Node | null
  onInstalled?: () => void
}

export default function Awg2InstallPrompt({ health, activeNode, onInstalled }: Awg2InstallPromptProps) {
  const nodeLabel = formatAwg2NodeLabel(health, activeNode)
  const installCmd = health?.install_command?.trim() || AWG2_INSTALL_CMD

  return (
    <div className="rounded-xl border bg-card/50 p-6">
      <EmptyState
        icon={CloudOff}
        title="Слой не установлен"
        description={`На узле ${nodeLabel} AZ-AWG2 (az-awg2) не обнаружен. Управление клиентами появится после установки слоя на сервере.`}
      />
      <div className="mx-auto mt-2 max-w-xl space-y-3">
        <div className="flex items-start gap-2 rounded-lg border bg-muted/30 p-3 text-sm">
          <Server className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <p className="text-muted-foreground">
            Уже установили на другом VPN-сервере? Выберите его в селекторе узла справа вверху. Для
            install-base и возможной перезагрузки используйте SSH.
          </p>
        </div>
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Установка на текущем узле (root):</p>
          <pre className="overflow-x-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs">{installCmd}</pre>
        </div>
        <div className="flex flex-wrap justify-center gap-2 pt-1">
          <Awg2InstallDialog mode="install" triggerLabel="Установить из панели" onCompleted={onInstalled} />
          <Button variant="outline" size="sm" asChild>
            <Link to="/nodes">Перейти к узлам</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
