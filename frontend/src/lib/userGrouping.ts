import type { TrafficClientRow, VpnConfigHaInfo } from '@/types'

export const UNOWNED_USER_KEY = 'unowned'

/** Stable group id: `user:<id>` for a known owner, `unowned` otherwise. */
export type UserGroupKey = string

export interface TrafficUserGroup {
  key: UserGroupKey
  ownerId: number | null
  username: string
  rows: TrafficClientRow[]
  configsCount: number
  activeConfigsCount: number
  protocols: string[]
  totalReceived: number
  totalSent: number
  totalBytes: number
  trafficPeriod: number
  lastSeenAt: string | null
  isActive: boolean
  ha: VpnConfigHaInfo | null
}

export function userGroupKey(ownerId?: number | null): UserGroupKey {
  return ownerId == null ? UNOWNED_USER_KEY : `user:${ownerId}`
}

export function userGroupLabel(username?: string | null): string {
  return (username || '').trim() || 'Без владельца'
}

/** Aggregate traffic rows into per-user groups (one row per config/protocol). */
export function groupTrafficRowsByUser(rows: TrafficClientRow[]): TrafficUserGroup[] {
  const groups = new Map<UserGroupKey, TrafficUserGroup>()

  for (const row of rows) {
    const key = userGroupKey(row.owner_id)
    let group = groups.get(key)
    if (!group) {
      group = {
        key,
        ownerId: row.owner_id ?? null,
        username: userGroupLabel(row.owner_username),
        rows: [],
        configsCount: 0,
        activeConfigsCount: 0,
        protocols: [],
        totalReceived: 0,
        totalSent: 0,
        totalBytes: 0,
        trafficPeriod: 0,
        lastSeenAt: null,
        isActive: false,
        ha: null,
      }
      groups.set(key, group)
    }
    group.rows.push(row)
    group.configsCount += 1
    if (row.is_active) group.activeConfigsCount += 1
    const protocol = (row.protocol_type || '').toLowerCase()
    if (protocol && !group.protocols.includes(protocol)) group.protocols.push(protocol)
    group.totalReceived += row.total_received
    group.totalSent += row.total_sent
    group.totalBytes += row.total_bytes
    group.trafficPeriod += row.traffic_period
    group.isActive = group.isActive || row.is_active
    group.ha = group.ha ?? row.ha ?? null
    if (row.last_seen_at && (!group.lastSeenAt || row.last_seen_at > group.lastSeenAt)) {
      group.lastSeenAt = row.last_seen_at
    }
  }

  return [...groups.values()].sort(
    (a, b) => b.totalBytes - a.totalBytes || a.username.localeCompare(b.username, 'ru'),
  )
}
