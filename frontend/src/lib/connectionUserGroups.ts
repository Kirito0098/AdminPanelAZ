import { UNOWNED_USER_KEY, userGroupLabel } from './userGrouping'

/** Minimal shape the NOC connection list needs for per-user grouping. */
export interface OwnerGroupableConnection {
  ownerId?: number | null
  ownerName?: string | null
  protocol: string
  online: boolean
  rx: number
  tx: number
  nodeName?: string | null
  activeNodeName?: string | null
  sortTime: number
}

export interface ConnectionOwnerGroup<T extends OwnerGroupableConnection> {
  key: string
  ownerId: number | null
  ownerName: string
  rows: T[]
  connectionsCount: number
  onlineCount: number
  rx: number
  tx: number
  protocols: string[]
  nodes: string[]
  lastActivity: number
}

export function connectionOwnerGroupKey(ownerId?: number | null): string {
  return ownerId == null ? UNOWNED_USER_KEY : `user:${ownerId}`
}

/**
 * Group live connections by owning user. Rows keep their incoming order (the
 * connection list already sorts them), groups go online-first and by traffic.
 */
export function groupConnectionsByOwner<T extends OwnerGroupableConnection>(
  rows: T[],
): ConnectionOwnerGroup<T>[] {
  const groups = new Map<string, ConnectionOwnerGroup<T>>()

  for (const row of rows) {
    const key = connectionOwnerGroupKey(row.ownerId)
    let group = groups.get(key)
    if (!group) {
      group = {
        key,
        ownerId: row.ownerId ?? null,
        ownerName: userGroupLabel(row.ownerName),
        rows: [],
        connectionsCount: 0,
        onlineCount: 0,
        rx: 0,
        tx: 0,
        protocols: [],
        nodes: [],
        lastActivity: 0,
      }
      groups.set(key, group)
    }
    group.rows.push(row)
    group.connectionsCount += 1
    if (row.online) group.onlineCount += 1
    group.rx += row.rx
    group.tx += row.tx
    if (!group.protocols.includes(row.protocol)) group.protocols.push(row.protocol)
    const node = row.activeNodeName || row.nodeName
    if (node && !group.nodes.includes(node)) group.nodes.push(node)
    group.lastActivity = Math.max(group.lastActivity, row.sortTime)
  }

  return [...groups.values()].sort(
    (a, b) =>
      b.onlineCount - a.onlineCount ||
      b.rx + b.tx - (a.rx + a.tx) ||
      a.ownerName.localeCompare(b.ownerName, 'ru'),
  )
}
