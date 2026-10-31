import type { NotificationItem } from '@/api/notifications'

/** Куда ведёт карточка уведомления; null — перехода нет. */
export function pathForNotification(item: NotificationItem): string | null {
  const requestId = item.action_payload?.request_id
  if (item.event_type.startsWith('access_request_') || item.category === 'requests') {
    if (typeof requestId === 'number' && Number.isFinite(requestId)) {
      return `/users?request=${requestId}`
    }
    return '/users?requests=1'
  }
  if (item.category === 'security') return '/logs'
  if (item.category === 'nodes') return '/nodes'
  if (item.category === 'services') return '/monitoring'
  const userId = item.action_payload?.user_id
  if (typeof userId === 'number' && Number.isFinite(userId)) return '/users'
  return null
}
