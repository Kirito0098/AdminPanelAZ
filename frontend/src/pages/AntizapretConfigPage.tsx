import { Settings2 } from 'lucide-react'
import { Navigate } from 'react-router-dom'
import AntizapretConfigTab from '@/components/routing/AntizapretConfigTab'
import { NodeBadge } from '@/components/NodeSelector'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'

export default function AntizapretConfigPage() {
  const { user } = useAuth()
  const { activeNode } = useNode()

  if (user?.role !== 'admin') {
    return <Navigate to="/routing" replace />
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Settings2 size={20} />
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Конфиг AntiZapret</h2>
            <p className="text-sm text-muted-foreground">
              Параметры файла setup на активном узле: маршрутизация трафика, WARP, безопасность и хосты
            </p>
          </div>
        </div>
        {activeNode && <NodeBadge name={activeNode.name} status={activeNode.status} />}
      </header>

      <AntizapretConfigTab />
    </div>
  )
}
