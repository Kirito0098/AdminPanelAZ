import type { ActionLogEntry } from '@/types'

export type ActionLogGroup = {
  id: string
  username: string | null | undefined
  action: string
  details: string | null | undefined
  entries: ActionLogEntry[]
}

function groupKey(entry: ActionLogEntry): string {
  return `${entry.username ?? ''}\0${entry.action}\0${entry.details ?? ''}`
}

/** Группирует подряд идущие записи с одинаковым пользователем, действием и деталями. */
export function groupConsecutiveActionLogs(entries: ActionLogEntry[]): ActionLogGroup[] {
  const groups: ActionLogGroup[] = []

  for (const entry of entries) {
    const last = groups[groups.length - 1]
    if (last && groupKey(last.entries[0]) === groupKey(entry)) {
      last.entries.push(entry)
      continue
    }

    groups.push({
      id: String(entry.id),
      username: entry.username,
      action: entry.action,
      details: entry.details,
      entries: [entry],
    })
  }

  return groups
}
