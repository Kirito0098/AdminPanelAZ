import { formatDateTime } from '@/lib/datetime'
import type { Node } from '@/types'

export function getSelectedNodes(nodes: Node[], selectedNodeIds: number[]) {
  const idSet = new Set(selectedNodeIds)
  return nodes.filter((node) => idSet.has(node.id))
}

export function getNodeMeta(node: Node) {
  const meta = node.metadata ?? {}
  const servicesActive = typeof meta.services_active === 'number' ? meta.services_active : null
  const servicesTotal = typeof meta.services_total === 'number' ? meta.services_total : null
  return {
    serverIp: typeof meta.server_ip === 'string' ? meta.server_ip : null,
    servicesLabel:
      servicesActive !== null && servicesTotal !== null ? `${servicesActive}/${servicesTotal}` : null,
    agentVersion: typeof meta.agent_version === 'string' ? meta.agent_version : null,
    lastError: typeof meta.last_error === 'string' ? meta.last_error : null,
  }
}

export function formatLastSeen(lastSeen?: string | null) {
  if (!lastSeen) return null
  return formatDateTime(lastSeen)
}

export function isWrongVersionSslError(error: string) {
  return /WRONG_VERSION_NUMBER|wrong version number/i.test(error)
}
