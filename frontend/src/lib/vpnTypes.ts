/** Канонический порядок протоколов в UI: WG/AWG 1.5 — одна категория. */
export const PROTOCOL_ORDER = ['openvpn', 'wireguard', 'amneziawg2'] as const
export type Protocol = (typeof PROTOCOL_ORDER)[number]

/** Полные имена — только для пояснительного текста, не для бейджей. */
const PROTOCOL_FULL_LABELS: Record<string, string> = {
  openvpn: 'OpenVPN',
  wireguard: 'WireGuard',
  amneziawg: 'AmneziaWG',
  amneziawg2: 'AmneziaWG 2.0',
}

/** Единые подписи протоколов для бейджей и фильтров. */
const PROTOCOL_BADGE_LABELS: Record<string, string> = {
  openvpn: 'OpenVPN',
  wireguard: 'WG/AWG 1.5',
  amneziawg: 'WG/AWG 1.5',
  amneziawg2: 'AWG 2.0',
}

/** Подписи модулей в настройках: WireGuard и AmneziaWG 1.5 — отдельные модули. */
const PROTOCOL_MODULE_LABELS: Record<string, string> = {
  openvpn: 'OpenVPN',
  wireguard: 'WireGuard',
  amneziawg: 'AmneziaWG 1.5',
  amneziawg2: 'AWG 2.0',
}

const PROTOCOL_ALIASES: Record<string, string> = {
  ovpn: 'openvpn',
  wg: 'wireguard',
  'wg 1.5': 'wireguard',
  'wg/awg 1.5': 'wireguard',
  awg: 'amneziawg',
  'awg 1.5': 'amneziawg',
  awg2: 'amneziawg2',
  'awg 2.0': 'amneziawg2',
  'amneziawg 2.0': 'amneziawg2',
  'wg 2.0': 'amneziawg2',
}

/** Приводит алиас/сырой id к каноническому ключу; неизвестное возвращает как есть. */
export function protocolKey(protocol: string): string {
  const value = (protocol || '').trim().toLowerCase()
  return PROTOCOL_ALIASES[value] ?? value
}

/** Полное имя протокола для пояснений: openvpn → OpenVPN. */
export function protocolFullLabel(protocol: string): string {
  const key = protocolKey(protocol)
  return PROTOCOL_FULL_LABELS[key] ?? protocol
}

/** Совместимый алиас полного имени (используется в прозе). */
export function vpnTypeLabel(type: string): string {
  return protocolFullLabel(type)
}

/** Единая подпись протокола в бейджах: WireGuard/AmneziaWG → WG/AWG 1.5. */
export function protocolLabel(protocol: string): string {
  const key = protocolKey(protocol)
  return PROTOCOL_BADGE_LABELS[key] ?? PROTOCOL_FULL_LABELS[key] ?? protocol
}

/** Подпись отдельного модуля в настройках: WireGuard / AmneziaWG 1.5 / AWG 2.0. */
export function protocolModuleLabel(protocol: string): string {
  const key = protocolKey(protocol)
  return PROTOCOL_MODULE_LABELS[key] ?? PROTOCOL_FULL_LABELS[key] ?? protocol
}

/**
 * Единый цвет бейджа — по брендовым цветам логотипов:
 * OpenVPN #EA7E20, WireGuard/AmneziaWG #88171A, AmneziaWG 2.0 #264B79.
 */
export function protocolBadgeClass(protocol: string): string {
  switch (protocolKey(protocol)) {
    case 'openvpn':
      return 'border-[#EA7E20]/40 bg-[#EA7E20]/10 text-[#A8560E] dark:text-[#F0A24F]'
    case 'wireguard':
    case 'amneziawg':
      return 'border-[#88171A]/40 bg-[#88171A]/10 text-[#88171A] dark:text-[#F07174]'
    case 'amneziawg2':
      return 'border-[#264B79]/40 bg-[#264B79]/10 text-[#264B79] dark:text-[#8FB4E8]'
    default:
      return 'border-border bg-muted text-muted-foreground'
  }
}

/**
 * Палитра графиков: брендовые оттенки, осветлённые для читаемости линий
 * на тёмной и светлой теме. Не использовать для текста бейджей.
 */
export const PROTOCOL_CHART_COLORS = {
  openvpn: '#EA7E20',
  wireguard: '#D14343',
  amneziawg2: '#4F7FBF',
  total: '#8A94A6',
} as const
