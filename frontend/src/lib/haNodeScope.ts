import type { Node, NodeHaContext, NodeSyncGroup } from '@/types'

export const HA_GROUP_SCOPE_PREFIXES = [
  '/traffic',
  '/routing',
  '/antizapret',
  '/edit-files',
  '/settings',
] as const

export function normalizePathname(pathname: string): string {
  if (!pathname || pathname === '/') return '/'
  return pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
}

export function isHaGroupScopePath(pathname: string): boolean {
  const path = normalizePathname(pathname)
  if (path === '/') return true
  return HA_GROUP_SCOPE_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))
}

export type HaSelectorOption =
  | {
      type: 'group'
      key: string
      groupId: number
      label: string
      primaryNodeId: number
      sharedDomain: string
      primaryStatus: Node['status']
    }
  | {
      type: 'node'
      key: string
      nodeId: number
      label: string
      status: Node['status']
      isLocal: boolean
    }

export function buildHaSelectorOptions(nodes: Node[], syncGroups: NodeSyncGroup[]): HaSelectorOption[] {
  const groupedNodeIds = new Set<number>()

  for (const group of syncGroups) {
    groupedNodeIds.add(group.primary_node_id)
    for (const replicaId of group.replica_node_ids) {
      groupedNodeIds.add(replicaId)
    }
  }

  const groupOptions: HaSelectorOption[] = syncGroups
    .map((group) => {
      const primary = nodes.find((node) => node.id === group.primary_node_id)
      return {
        type: 'group' as const,
        key: `group:${group.id}`,
        groupId: group.id,
        label: group.name,
        primaryNodeId: group.primary_node_id,
        sharedDomain: group.shared_domain,
        primaryStatus: primary?.status ?? 'unknown',
      }
    })
    .sort((a, b) => a.label.localeCompare(b.label, 'ru'))

  const standaloneOptions: HaSelectorOption[] = nodes
    .filter((node) => !groupedNodeIds.has(node.id))
    .sort((a, b) => a.name.localeCompare(b.name, 'ru'))
    .map((node) => ({
      type: 'node' as const,
      key: `node:${node.id}`,
      nodeId: node.id,
      label: node.name,
      status: node.status,
      isLocal: node.is_local,
    }))

  return [...groupOptions, ...standaloneOptions]
}

export function resolveHaSelectorValue(
  activeNode: Node,
  activeNodeHa: NodeHaContext | null,
  syncGroups: NodeSyncGroup[],
): string {
  if (activeNodeHa) {
    return `group:${activeNodeHa.sync_group_id}`
  }

  const containingGroup = syncGroups.find(
    (group) =>
      group.primary_node_id === activeNode.id || group.replica_node_ids.includes(activeNode.id),
  )
  if (containingGroup) {
    return `group:${containingGroup.id}`
  }

  return `node:${activeNode.id}`
}

export function getHaScopeDisplayLabel(
  activeNodeHa: NodeHaContext | null,
  activeNode: Node,
  isHaScope: boolean,
): string {
  if (isHaScope && activeNodeHa?.group_name) {
    return activeNodeHa.group_name
  }
  return activeNode.name
}
