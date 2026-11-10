import { apiFetch } from './http'
import { openTicketEventSource, type StreamHandle } from './streamTicket'

export type NotificationCategory = 'requests' | 'security' | 'nodes' | 'services' | 'tasks'
export type NotificationLevel = 'info' | 'warning' | 'error'

export interface NotificationState {
  read: boolean
  hidden: boolean
  snoozed_until: string | null
}

export interface NotificationDetailsEntry {
  label: string
  value: string
}

export interface NotificationItem {
  id: number
  category: NotificationCategory
  level: NotificationLevel | string
  event_type: string
  title: string
  message: string
  created_at: string
  action_payload?: Record<string, unknown> | null
  details: NotificationDetailsEntry[]
  state: NotificationState
}

export interface NotificationCategoryCount {
  total: number
  unread: number
}

export interface NotificationCounts {
  unread: number
  attention: number
  snoozed: number
  hidden: number
  by_category: Record<string, NotificationCategoryCount>
}

export interface NotificationsResponse {
  items: NotificationItem[]
  unread_count: number
  pending_requests_count: number
  counts: NotificationCounts
}

export interface NotificationPreferences {
  categories: Record<NotificationCategory, boolean>
}

export interface BellNotifyAdmin {
  user_id: number
  username: string
  categories: Record<NotificationCategory, boolean>
}

export async function fetchBellNotifyAdmins(): Promise<BellNotifyAdmin[]> {
  const data = await apiFetch<{ admins: BellNotifyAdmin[] }>('/notifications/admins')
  return data.admins
}

export async function saveBellNotifyAdmin(
  userId: number,
  categories: Record<NotificationCategory, boolean>,
): Promise<BellNotifyAdmin> {
  return apiFetch<BellNotifyAdmin>(`/notifications/admins/${userId}`, {
    method: 'PUT',
    body: JSON.stringify({ categories }),
  })
}

export async function fetchNotificationPreferences(): Promise<NotificationPreferences> {
  return apiFetch<NotificationPreferences>('/notifications/preferences')
}

export interface NotificationFilters {
  category?: NotificationCategory
  level?: NotificationLevel
  unread_only?: boolean
  q?: string
  hidden_only?: boolean
  limit?: number
  before_id?: number
}

export async function fetchNotifications(params?: NotificationFilters): Promise<NotificationsResponse> {
  const search = new URLSearchParams()
  if (params?.category) search.set('category', params.category)
  if (params?.level) search.set('level', params.level)
  if (params?.unread_only) search.set('unread_only', 'true')
  if (params?.q) search.set('q', params.q)
  if (params?.hidden_only) search.set('hidden_only', 'true')
  if (params?.limit) search.set('limit', String(params.limit))
  if (params?.before_id) search.set('before_id', String(params.before_id))
  const qs = search.toString()
  return apiFetch<NotificationsResponse>(qs ? `/notifications?${qs}` : '/notifications')
}

export interface NotificationStatePatch {
  read?: boolean
  hidden?: boolean
  snoozed_until?: string | null
}

export async function setNotificationState(
  id: number,
  patch: NotificationStatePatch,
): Promise<{ state: NotificationState }> {
  return apiFetch<{ state: NotificationState }>(`/notifications/${id}/state`, {
    method: 'POST',
    body: JSON.stringify(patch),
  })
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

