/** Протоколы, которые можно включить в план абонента и unlock-ключ. */
export const REQUEST_PROTOCOLS: { id: string; featureKeys: string[] }[] = [
  { id: 'wireguard', featureKeys: ['wireguard', 'amneziawg'] },
  { id: 'openvpn', featureKeys: ['openvpn'] },
  { id: 'amneziawg2', featureKeys: ['awg2'] },
]

export const REQUEST_TYPE_LABELS: Record<string, string> = {
  new_user: 'Новый пользователь',
  add_config: 'Дополнительный конфиг',
  extend_access: 'Продление доступа',
}
