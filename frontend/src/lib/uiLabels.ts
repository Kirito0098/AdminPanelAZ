import type { NodeStatus } from '@/types'

/** Статус узла для подписей в UI. */
export const NODE_STATUS_LABELS: Record<NodeStatus, string> = {
  online: 'В сети',
  offline: 'Не в сети',
  unknown: 'Неизвестно',
}

export function nodeStatusRu(status: string): string {
  if (status === 'online') return NODE_STATUS_LABELS.online
  if (status === 'offline') return NODE_STATUS_LABELS.offline
  if (status === 'unknown') return NODE_STATUS_LABELS.unknown
  return status
}

/** Узлы с status === online (для фильтров и подписей). */
export const NODES_ONLINE_PHRASE = 'узлы в сети'
export const ALL_NODES_ONLINE_PHRASE = 'Все узлы в сети'

/** Источник данных в журналах / мониторинге. */
export function connectionSourceLabel(source: string): string {
  if (source === 'management_socket') return 'Сокет управления'
  return source
}

/** Заголовки колонок подключений. */
export const COL_REAL_IP = 'Реальный IP'
export const COL_VPN_IP = 'IP в VPN'
export const COL_HANDSHAKE = 'Рукопожатие'
export const COL_CONNECTED_SINCE = 'Подключён с'

/** HA / синхронизация узлов. */
export const HA_PRIMARY = 'Основной'
export const HA_REPLICA = 'Реплика'
export const HA_PUSH_FULL = 'Полная синхронизация'
export const HA_AUTO_SYNC_TITLE = 'Авто-синхронизация HA'
