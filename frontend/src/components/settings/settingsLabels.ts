import type { SettingsSection } from '@/components/settings/SettingsNav'
import type { UserRole } from '@/types'

export interface SectionMeta {
  title: string
  description: string
  hint?: string
}

export const SECTION_META: Record<SettingsSection, SectionMeta> = {
  personal: {
    title: 'Мой профиль',
    description: 'Внешний вид, пароль и дополнительная защита при входе',
    hint: 'Здесь настраивается только ваш личный аккаунт — остальные разделы видны администраторам.',
  },
  users: {
    title: 'Пользователи',
    description: 'Кто может входить в панель и что ему разрешено делать',
    hint: 'Администратор управляет всем. Пользователь работает с VPN. Режим «Только просмотр» — только смотреть выбранные конфиги.',
  },
  security: {
    title: 'Защита входа',
    description: 'Ограничение доступа по IP и блокировка подозрительных подключений',
    hint: 'Полезно, если панель доступна из интернета: можно разрешить вход только с ваших адресов.',
  },
  config_delivery: {
    title: 'Выдача VPN-профилей',
    description: 'QR-коды для телефона и готовые файлы для роутеров',
    hint: 'Клиенты могут скачать профиль по ссылке или QR без входа в панель — если вы это включите.',
  },
  maintenance: {
    title: 'Обслуживание VPN',
    description: 'Обновление профилей клиентов, очистка старых данных и перезапуск служб',
    hint: 'Операции в этом разделе могут временно прервать VPN-подключения. Лучше выполнять в спокойное время.',
  },
  backup: {
    title: 'Резервные копии',
    description: 'Сохранение и восстановление настроек панели',
    hint: 'Перед крупными изменениями рекомендуется сделать копию — так проще откатиться при ошибке.',
  },
  monitoring: {
    title: 'Нагрузка и уведомления',
    description: 'Когда предупреждать о высокой нагрузке и куда отправлять сообщения',
    hint: 'Можно получать оповещения в Telegram, если на сервере заканчивается память или процессор перегружен.',
  },
  vpn_network: {
    title: 'Адрес сайта и HTTPS',
    description: 'Как панель открывается в браузере: домен, защищённое соединение и прокси',
    hint: 'Настройте, если панель должна открываться по вашему домену с замочком HTTPS.',
  },
  modules: {
    title: 'Разделы панели',
    description: 'Какие функции включены и сколько ресурсов они потребляют',
    hint: 'Можно отключить ненужные разделы или выбрать режим «экономия» на слабом сервере.',
  },
  updates: {
    title: 'Обновление панели',
    description: 'Проверка и установка новых версий',
    hint: 'Перед обновлением сделайте резервную копию. Процесс может занять до 15–20 минут — не прерывайте его.',
  },
  panel_ops: {
    title: 'Перезапуск и пересборка',
    description: 'Сборка интерфейса и перезапуск сервиса adminpanelaz',
    hint: 'Сборка интерфейса может занять продолжительное время на слабом сервере. Дождитесь завершения, не запускайте повторно.',
  },
  tests: {
    title: 'Проверка работы',
    description: 'Автоматическая диагностика: всё ли запущено и открывается ли сайт',
    hint: 'Если что-то не работает — запустите проверку, она подскажет, где искать проблему.',
  },
}

export function getSectionMeta(section: SettingsSection): SectionMeta {
  return SECTION_META[section]
}

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Администратор',
  user: 'Пользователь',
  viewer: 'Только просмотр',
}

export const ROLE_HINTS: Record<UserRole, string> = {
  admin: 'Полный доступ ко всем настройкам и VPN',
  user: 'Работа с VPN-клиентами в рамках своих прав',
  viewer: 'Только просмотр и скачивание выбранных конфигов',
}

export const VPN_SERVICE_LABELS: Record<string, string> = {
  'openvpn-server@antizapret-udp': 'OpenVPN AntiZapret (UDP)',
  'openvpn-server@antizapret-tcp': 'OpenVPN AntiZapret (TCP)',
  'openvpn-server@vpn-udp': 'OpenVPN VPN (UDP)',
  'openvpn-server@vpn-tcp': 'OpenVPN VPN (TCP)',
  'wg-quick@antizapret': 'WireGuard AntiZapret',
  'wg-quick@vpn': 'WireGuard VPN',
}

export function getVpnServiceLabel(service: string): string {
  return VPN_SERVICE_LABELS[service] ?? service
}
