import type { NotificationItem } from '@/api/notifications'
import { isSnoozed } from './time'

/**
 * «Непрочитано» на клиенте — то же правило, что `is_unread` на сервере:
 * не прочитано, не скрыто и не отложено до будущего времени.
 */
export function isUnread(item: NotificationItem): boolean {
  return !item.state.read && !item.state.hidden && !isSnoozed(item.state.snoozed_until)
}
