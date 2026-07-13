import type { User, UserRole } from '@/types'

const roleLabels: Record<UserRole, string> = {
  admin: 'Администратор',
  user: 'Пользователь',
}

export function configOwnerCandidates(users: User[]): User[] {
  return users
    .filter((user) => user.is_active && (user.role === 'admin' || user.role === 'user'))
    .sort((a, b) => a.username.localeCompare(b.username, 'ru'))
}

export function formatOwnerLabel(user: Pick<User, 'username' | 'role'>, inactive = false): string {
  if (inactive) {
    return `${user.username} (неактивен)`
  }
  return `${user.username} (${roleLabels[user.role]})`
}

export function resolveOwnerOptions(
  users: User[],
  selectedId: number | null,
  fallback?: { id: number; username: string },
): User[] {
  const candidates = configOwnerCandidates(users)
  if (selectedId && fallback && !candidates.some((user) => user.id === selectedId)) {
    return [
      {
        id: fallback.id,
        username: fallback.username,
        role: 'user',
        theme: 'dark',
        is_active: false,
        must_change_password: false,
        created_at: '',
      },
      ...candidates,
    ]
  }
  return candidates
}
