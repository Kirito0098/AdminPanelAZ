import type { NotificationItem } from '@/api/notifications'

/** Куда ведёт карточка уведомления; null — перехода нет. */
export function pathForNotification(item: NotificationItem): string | null {
  const requestId = item.action_payload?.request_id
  const userId = item.action_payload?.user_id
  // Сообщения абонента открывают диалог в разделе «Сообщения».
  if (item.event_type === 'user_message') {
    if (typeof userId === 'number' && Number.isFinite(userId)) return `/messages?user=${userId}`
    return '/messages'
  }
  if (item.event_type.startsWith('access_request_') || item.category === 'requests') {
    if (typeof requestId === 'number' && Number.isFinite(requestId)) {
      return `/users?request=${requestId}`
    }
    return '/users?requests=1'
  }
  if (item.category === 'security') return '/monitoring?tab=logs'
  if (item.category === 'nodes') return '/nodes'
  if (item.category === 'services') return '/monitoring'
  if (typeof userId === 'number' && Number.isFinite(userId)) return '/users'
  return null
}
