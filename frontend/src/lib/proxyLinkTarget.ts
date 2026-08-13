import { buildHaSelectorOptions, type HaSelectorOption } from '@/lib/haNodeScope'
import { findNodeHaMembership } from '@/lib/nodeHa'
import type { Node, NodeSyncGroup } from '@/types'

export const PROXY_LINK_NONE = 'none'

export type ProxyLinkTarget = {
  kind: 'ha' | 'vpn' | 'missing'
  /** e.g. HA «Europe» or vpn-eu-1 */
  label: string
  /** Group or node name without prefix */
  shortLabel: string
  vpnNodeId: number
  vpnNodeName?: string
  haGroupId?: number
  haGroupName?: string
}

export function resolveProxyLinkTarget(
  linkedVpnNodeId: number | null | undefined,
  nodes: Node[],
  syncGroups: NodeSyncGroup[],
): ProxyLinkTarget | null {
  if (linkedVpnNodeId == null) return null

  const vpn = nodes.find((node) => node.id === linkedVpnNodeId)
  const membership = findNodeHaMembership(linkedVpnNodeId, syncGroups)

  if (membership) {
    return {
      kind: 'ha',
      label: `HA «${membership.groupName}»`,
      shortLabel: membership.groupName,
      vpnNodeId: linkedVpnNodeId,
      vpnNodeName: vpn?.name,
      haGroupId: membership.groupId,
      haGroupName: membership.groupName,
    }
  }

  if (vpn) {
    return {
      kind: 'vpn',
      label: vpn.name,
      shortLabel: vpn.name,
      vpnNodeId: linkedVpnNodeId,
      vpnNodeName: vpn.name,
    }
  }

  return {
    kind: 'missing',
    label: `узел #${linkedVpnNodeId} (не найден)`,
    shortLabel: `#${linkedVpnNodeId}`,
    vpnNodeId: linkedVpnNodeId,
  }
}

/** Select value for create/edit forms (`none` | `group:id` | `node:id`). */
export function resolveProxyLinkSelectorValue(
  linkedVpnNodeId: number | null | undefined,
  nodes: Node[],
  syncGroups: NodeSyncGroup[],
): string {
  if (linkedVpnNodeId == null) return PROXY_LINK_NONE

  const membership = findNodeHaMembership(linkedVpnNodeId, syncGroups)
  if (membership) {
    return `group:${membership.groupId}`
  }

  if (nodes.some((node) => node.id === linkedVpnNodeId)) {
    return `node:${linkedVpnNodeId}`
  }

  // Orphan link: keep a node: key so the select can show a fallback item
  return `node:${linkedVpnNodeId}`
}

export function linkedVpnNodeIdFromSelectorValue(
  value: string,
  options: HaSelectorOption[],
): number | null {
  if (!value || value === PROXY_LINK_NONE) return null

  if (value.startsWith('group:')) {
    const groupId = Number(value.slice('group:'.length))
    const option = options.find((item) => item.type === 'group' && item.groupId === groupId)
    return option && option.type === 'group' ? option.primaryNodeId : null
  }

  if (value.startsWith('node:')) {
    const nodeId = Number(value.slice('node:'.length))
    return Number.isFinite(nodeId) && nodeId > 0 ? nodeId : null
  }

  return null
}

export function proxyLinkSelectorOptions(nodes: Node[], syncGroups: NodeSyncGroup[]): HaSelectorOption[] {
  return buildHaSelectorOptions(nodes, syncGroups)
}
