/** Протоколы, которые можно включить в план абонента и unlock-ключ. */
export const REQUEST_PROTOCOLS: { id: string; label: string; featureKeys: string[] }[] = [
  { id: 'wireguard', label: 'WireGuard', featureKeys: ['wireguard', 'amneziawg'] },
  { id: 'openvpn', label: 'OpenVPN', featureKeys: ['openvpn'] },
  { id: 'amneziawg2', label: 'AmneziaWG 2.0', featureKeys: ['awg2'] },
]

export const REQUEST_TYPE_LABELS: Record<string, string> = {
  new_user: 'Новый пользователь',
  add_config: 'Дополнительный конфиг',
  extend_access: 'Продление доступа',
}
