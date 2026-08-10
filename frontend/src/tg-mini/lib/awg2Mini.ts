import type { TgMiniAwg2Status } from '@/types'

export type Awg2StatusTone = 'success' | 'warning' | 'destructive' | 'secondary'

export function awg2StatusMeta(data: TgMiniAwg2Status | null): {
  label: string
  tone: Awg2StatusTone
} {
  if (!data) {
    return { label: 'Нет данных', tone: 'secondary' }
  }
  if (data.health_error && !data.installed) {
    return { label: 'Ошибка', tone: 'destructive' }
  }
  if (!data.installed) {
    return { label: 'Не установлен', tone: 'warning' }
  }
  if (data.online_count > 0) {
    return { label: 'Online', tone: 'success' }
  }
  return { label: 'Установлен', tone: 'secondary' }
}

export function awg2NodeLabel(data: TgMiniAwg2Status): string {
  if (data.node_name && data.node_host) {
    return `${data.node_name} · ${data.node_host}`
  }
  return data.node_name || data.node_host || 'активный узел'
}
