import type { UserRole } from '@/types'

export const MINI_ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Администратор',
  user: 'Пользователь',
}

export function miniRoleLabel(role?: string | null): string {
  if (!role) return '—'
  return MINI_ROLE_LABELS[role as UserRole] ?? role
}
