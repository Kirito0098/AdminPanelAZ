import { apiFetch } from './http'
import { openTicketEventSource, type StreamHandle } from './streamTicket'

export type NotificationCategory = 'requests' | 'security' | 'nodes' | 'services' | 'tasks'

export interface NotificationItem {
  id: number
  category: NotificationCategory
  level: string
  event_type: string
  title: string
  message: string
  created_at: string
}

export interface NotificationsResponse {
  items: NotificationItem[]
  unread_count: number
  pending_requests_count: number
}

export async function fetchNotifications(params?: {
  category?: NotificationCategory
  limit?: number
  before_id?: number
}): Promise<NotificationsResponse> {
  const q = new URLSearchParams()
  if (params?.category) q.set('category', params.category)
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.before_id) q.set('before_id', String(params.before_id))
  const qs = q.toString()
  const path = qs ? `/notifications?${qs}` : '/notifications'
  return apiFetch<NotificationsResponse>(path)
}

export async function markNotificationsRead(up_to_id: number) {
  return apiFetch('/notifications/read', {
    method: 'POST',
    body: JSON.stringify({ up_to_id }),
  })
}

export function openNotificationsStream(onUpdate: (data: unknown) => void): StreamHandle {
  return openTicketEventSource({
    stream: 'notifications',
    path: '/notifications/stream',
    reconnectDelayMs: 3000,
    attach: (source) => {
      source.addEventListener('update', (ev) => {
        if (ev instanceof MessageEvent) onUpdate(JSON.parse(String(ev.data)))
      })
    },
  })
}
