import type { TgMiniWarperStatus } from '@/types'

export type WarperStatusTone = 'success' | 'warning' | 'destructive' | 'secondary'

export function warperStatusMeta(data: TgMiniWarperStatus | null): {
  label: string
  tone: WarperStatusTone
} {
  if (!data) {
    return { label: 'Нет данных', tone: 'secondary' }
  }
  if (data.conflict_antizapret_warp) {
    return { label: 'Конфликт WARP', tone: 'destructive' }
  }
  if (data.health_error && !data.installed) {
    return { label: 'Ошибка', tone: 'destructive' }
  }
  if (!data.installed) {
    return { label: 'Не установлен', tone: 'warning' }
  }
  if (data.active) {
    return { label: 'Активен', tone: 'success' }
  }
  return { label: 'Выключен', tone: 'secondary' }
}

export function warperNodeLabel(data: TgMiniWarperStatus): string {
  if (data.node_name && data.node_host) {
    return `${data.node_name} · ${data.node_host}`
  }
  return data.node_name || data.node_host || 'активный узел'
}
