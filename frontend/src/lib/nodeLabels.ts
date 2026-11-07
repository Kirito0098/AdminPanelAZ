import type { Node, User } from '@/types'

/** Node id → display name as shown across the panel (portal label wins). */
export function nodeLabelMap(nodes: Node[]): Map<number, string> {
  return new Map(nodes.map((node) => [node.id, node.portal_label || node.name]))
}

/** "Название (host)" из health-ответа сервиса, иначе из активного узла. */
export function nodeNameWithHost(
  health: { node_name?: string | null; node_host?: string | null } | null,
  activeNode: Pick<Node, 'name' | 'host'> | null,
): string {
  const name = health?.node_name ?? activeNode?.name
  const host = health?.node_host ?? activeNode?.host
  if (name && host) return `${name} (${host})`
  return name || host || 'активном узле панели'
}

/** Display names of a user's plan nodes; an unknown id (deleted node) keeps ``#id``. */
export function userNodeLabels(
  user: Pick<User, 'plan_node_ids'>,
  labels: Map<number, string>,
): string[] {
  return (user.plan_node_ids ?? []).map((id) => labels.get(id) ?? `#${id}`)
}
