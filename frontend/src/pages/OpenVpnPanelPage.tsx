import { useState } from 'react'
import { Cable, Server } from 'lucide-react'
import { Navigate } from 'react-router-dom'
import HaReplicaBanner from '@/components/dashboard/HaReplicaBanner'
import OpenVpnPanelTab from '@/components/routing/OpenVpnPanelTab'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import { Badge } from '@/components/ui/badge'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useHaReplicaReadonly } from '@/hooks/useHaReplicaReadonly'
import { DOCS } from '@/lib/docsUrls'

export default function OpenVpnPanelPage() {
  const { user } = useAuth()
  const { activeNode } = useNode()
  const haReplicaReadonly = useHaReplicaReadonly()
  const [remoteHostsDirty, setRemoteHostsDirty] = useState(false)

  if (user?.role !== 'admin') {
    return <Navigate to="/routing" replace />
  }

  return (
    <div className="space-y-6">
      <HaReplicaBanner />
      <PageSectionHeader
        icon={Cable}
        title="OpenVPN"
        titleAddon={
          <>
            {activeNode?.name && (
              <Badge variant="outline" className="gap-1.5">
                <Server className="h-3 w-3" />
                {activeNode.name}
              </Badge>
            )}
            {remoteHostsDirty && (
              <Badge
                variant="outline"
                className="border-amber-500/50 text-amber-700 dark:text-amber-300"
              >
                адреса не сохранены
              </Badge>
            )}
          </>
        }
        description="Адреса в профилях, multihome, DNS и состояние установки"
        docsHref={DOCS.antizapretConfig}
      />
      <OpenVpnPanelTab
        activeNodeId={activeNode?.id ?? null}
        nodeName={activeNode?.name ?? null}
        disabled={haReplicaReadonly}
        onDirtyChange={setRemoteHostsDirty}
      />
    </div>
  )
}
