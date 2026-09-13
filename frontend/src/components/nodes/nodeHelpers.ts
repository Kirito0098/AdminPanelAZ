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
  const lastLinkError =
    meta.last_link_error && typeof meta.last_link_error === 'object'
      ? (meta.last_link_error as { code?: string; message?: string; hint?: string; at?: string })
      : null
  return {
    serverIp: typeof meta.server_ip === 'string' ? meta.server_ip : null,
    servicesLabel:
      servicesActive !== null && servicesTotal !== null ? `${servicesActive}/${servicesTotal}` : null,
    agentVersion: typeof meta.agent_version === 'string' ? meta.agent_version : null,
    lastError: typeof meta.last_error === 'string' ? meta.last_error : null,
    lastHealthOkAt: typeof meta.last_health_ok_at === 'string' ? meta.last_health_ok_at : null,
    uptimeSec: typeof meta.uptime_sec === 'number' ? meta.uptime_sec : null,
    listenTls: typeof meta.listen_tls === 'boolean' ? meta.listen_tls : null,
    expectedTls: typeof meta.expected_tls === 'boolean' ? meta.expected_tls : null,
    tlsMismatch: Boolean(meta.tls_mismatch),
    lastLinkError,
  }
}

export function formatLastSeen(lastSeen?: string | null) {
  if (!lastSeen) return null
  return formatDateTime(lastSeen)
}

export function isWrongVersionSslError(error: string) {
  return /WRONG_VERSION_NUMBER|wrong version number/i.test(error)
}
