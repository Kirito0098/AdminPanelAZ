import { apiFetch } from './http'
import type { MessageThread, SendMessageResult, UserMessageItem } from '../types'

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const suffix = search.toString()
  return suffix ? `?${suffix}` : ''
}

export async function getMessageThreads(params: { q?: string; unread?: boolean } = {}) {
  return apiFetch<MessageThread[]>(
    `/messages/threads${query({ q: params.q, unread: params.unread ? 1 : undefined })}`,
  )
}

export async function getMessageUnreadCount() {
  return apiFetch<{ count: number }>('/messages/unread-count')
}

export async function getUserMessages(
  userId: number,
  params: { beforeId?: number; limit?: number } = {},
) {
  return apiFetch<UserMessageItem[]>(
    `/messages/${userId}${query({ before_id: params.beforeId, limit: params.limit })}`,
  )
}

export async function markMessagesRead(userId: number) {
  return apiFetch<{ marked: number }>(`/messages/${userId}/read`, { method: 'POST' })
}

export async function getUserUnreadCount(userId: number) {
  return apiFetch<{ count: number }>(`/messages/${userId}/unread`)
}

export async function sendUserMessage(userId: number, text: string) {
  return apiFetch<SendMessageResult>(`/messages/${userId}`, {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}
