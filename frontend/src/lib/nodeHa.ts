import type { Node, NodeSyncGroup } from '@/types'

export type NodeHaMembership = {
  groupId: number
  groupName: string
}

export function findNodeHaMembership(
  nodeId: number,
  groups: NodeSyncGroup[],
): NodeHaMembership | null {
  for (const group of groups) {
    if (group.primary_node_id === nodeId) {
      return { groupId: group.id, groupName: group.name }
    }
    if (group.replica_node_ids.includes(nodeId)) {
      return { groupId: group.id, groupName: group.name }
    }
  }
  return null
}

export function nodeDeleteBlockedMessage(node: Pick<Node, 'name'>, membership: NodeHaMembership): string {
  return (
    `Узел «${node.name}» входит в HA-группу «${membership.groupName}». ` +
    'Сначала расформируйте группу в разделе «Группы синхронизации» на этой странице.'
  )
}

export function nodeHaDeleteBlockedHint(): string {
  return (
    'Пока узел в HA-группе, удалить его из панели нельзя — иначе нарушится синхронизация primary и replica. ' +
    'Расформируйте группу: узлы останутся, конфиги на серверах сохранятся, после этого удаление станет доступно.'
  )
}
