import type { TgMiniNode } from '@/types'

/** Nodes that can host new client configs: no HA replicas and no proxy nodes. */
export function selectablePlanNodes(nodes: TgMiniNode[]): TgMiniNode[] {
  return nodes.filter(
    (node) => node.ha_role !== 'replica' && (node.node_kind || 'vpn') !== 'proxy',
  )
}
