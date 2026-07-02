const ROLE_LABELS: Record<string, string> = {
  admin: 'администратор',
  user: 'пользователь',
  viewer: 'наблюдатель',
}

const LOGIN_METHOD_LABELS: Record<string, string> = {
  passkey: 'Passkey',
  '2fa': '2FA',
  password: 'Пароль',
}

const DETAIL_KEY_LABELS: Record<string, string> = {
  telegram_id: 'ID Telegram',
  created: 'Пользователь',
  role: 'Роль',
  target: 'Пользователь',
  deleted: 'Удалён',
  name: 'Имя',
  id: 'ID',
  host: 'Хост',
  node: 'Узел',
  node_id: 'ID узла',
  nodes: 'Узлы',
  task_id: 'ID задачи',
  ip: 'IP',
  hours: 'Часы',
  mode: 'Режим',
  port: 'Порт',
  channel: 'Канал',
  router: 'Маршрутизатор',
  file: 'Файл',
  files: 'Файлы',
  from: 'Источник',
  success: 'Успешно',
  failed: 'Ошибки',
  doall: 'Запуск doall',
  action: 'Действие',
  days: 'Дней',
  block_until: 'Блок до',
  source: 'Источник',
  field: 'Поле',
  value: 'Значение',
  secret_id: 'Секрет',
  successful_replicas: 'Успешные реплики',
  failed_replicas: 'Неудачные реплики',
  cooldown: 'Пауза, сек',
}

const DETAIL_VALUE_LABELS: Record<string, string> = {
  passkey: 'Passkey',
  '2fa': '2FA',
  password: 'Пароль',
  'invalid credentials': 'Неверный логин или пароль',
  all_online: 'Все узлы в сети',
  active: 'Активный узел',
  'no-op': 'Без изменений',
  recreate_profiles: 'Пересоздание профилей',
  event_webhook_settings: 'Настройки webhook событий',
  audit_stream_settings: 'Настройки потока аудита',
  telegram_bot: 'Telegram-бот',
  register: 'Регистрация',
  delete: 'Удаление',
  test: 'Тест',
  token_change: 'Смена токена',
  doall: 'doall.sh',
  true: 'да',
  false: 'нет',
  вкл: 'включено',
  выкл: 'выключено',
}

const SECURITY_FIELD_LABELS: Record<string, string> = {
  ip_restriction_enabled: 'Ограничение по IP',
  block_scanners: 'Блокировка сканеров',
  allowed_ips: 'Разрешённые IP',
  login_rate_limit: 'Лимит попыток входа',
  captcha_after_failures: 'Капча после ошибок',
}

const BOOL_ON_OFF = /^(true|false|yes|no|1|0|вкл|выкл)$/i

function translateRole(value: string): string {
  return ROLE_LABELS[value.toLowerCase()] ?? value
}

function translateValue(key: string, value: string): string {
  if (key === 'role') return translateRole(value)
  if (key === 'value' && BOOL_ON_OFF.test(value)) {
    const lower = value.toLowerCase()
    if (['true', 'yes', '1', 'вкл'].includes(lower)) return 'включено'
    if (['false', 'no', '0', 'выкл'].includes(lower)) return 'выключено'
  }
  if (key === 'field' && SECURITY_FIELD_LABELS[value]) {
    return SECURITY_FIELD_LABELS[value]
  }
  return DETAIL_VALUE_LABELS[value] ?? DETAIL_VALUE_LABELS[value.toLowerCase()] ?? value
}

function translateKey(key: string): string {
  return DETAIL_KEY_LABELS[key] ?? key.replace(/_/g, ' ')
}

function parseDetailPairs(details: string): Array<[string, string]> {
  const pairs: Array<[string, string]> = []
  const tokens = details
    .replace(/;\s*/g, ' ')
    .replace(/,\s*(?=[\w.-]+=)/g, ' ')
    .split(/\s+(?=[\w.-]+=)/)

  for (const token of tokens) {
    const part = token.trim()
    if (!part) continue

    const eqIdx = part.indexOf('=')
    if (eqIdx === -1) continue

    const key = part.slice(0, eqIdx).trim()
    const value = part.slice(eqIdx + 1).trim().replace(/,$/, '')
    if (key) pairs.push([key, value])
  }

  return pairs
}

function formatPairs(pairs: Array<[string, string]>): string {
  return pairs
    .map(([key, value]) => `${translateKey(key)}: ${translateValue(key, value)}`)
    .join('; ')
}

function formatArrowChange(raw: string): string | null {
  if (!raw.includes('→')) return null
  const [from, to] = raw.split('→', 2).map((part) => part.trim())
  const fromLabel = DETAIL_VALUE_LABELS[from] ?? from
  const toLabel = DETAIL_VALUE_LABELS[to] ?? to
  return `с «${fromLabel}» на «${toLabel}»`
}

function formatClientDays(raw: string): string | null {
  const match = raw.match(/^(.+?)\s+(\d+)d$/)
  if (!match) return null
  return `Клиент ${match[1]}, ${match[2]} дн.`
}

function formatDisconnect(raw: string): string | null {
  const match = raw.match(/^(.+?)\s+\((.+?)\)\s+cooldown=(\d+)s$/)
  if (!match) return null
  return `Клиент ${match[1]}, профиль ${match[2]}, пауза ${match[3]} с`
}

function formatTrafficLimit(raw: string): string | null {
  const match = raw.match(/^(.+?)\s+(\d+(?:\.\d+)?)([A-Za-z]+)$/)
  if (!match) return null
  return `Клиент ${match[1]}, лимит ${match[2]} ${match[3]}`
}

function formatCidrDeployTarget(raw: string): string {
  if (raw === 'all_online') return 'Цель: все узлы в сети'
  if (raw === 'active') return 'Цель: активный узел'
  if (/^\d+$/.test(raw)) return `Цель: узел ${raw}`
  if (/^[\d,]+$/.test(raw)) {
    const ids = raw.split(',').map((id) => id.trim()).filter(Boolean)
    return `Цель: узлы ${ids.join(', ')}`
  }
  return `Цель: ${raw}`
}

function formatNodeRef(raw: string): string | null {
  const pairs = parseDetailPairs(raw)
  if (!pairs.length) return null
  const byKey = new Map(pairs)
  const name = byKey.get('name')
  const id = byKey.get('id')
  const host = byKey.get('host')
  if (name && id) return `Узел «${name}» (ID ${id})`
  if (name && host) return `Узел «${name}» (${host})`
  if (name) return `Узел «${name}»`
  return formatPairs(pairs)
}

function formatLoginSuccess(raw: string): string {
  const method = LOGIN_METHOD_LABELS[raw.toLowerCase()]
  if (method) return `Способ входа: ${method}`
  return raw
}

function formatUserCreate(raw: string): string {
  const pairs = parseDetailPairs(raw)
  const created = pairs.find(([key]) => key === 'created')?.[1]
  const role = pairs.find(([key]) => key === 'role')?.[1]
  if (created && role) {
    return `Пользователь «${created}», роль: ${translateRole(role)}`
  }
  return formatPairs(pairs)
}

function formatTelegramLink(raw: string): string {
  const pairs = parseDetailPairs(raw)
  const tgId = pairs.find(([key]) => key === 'telegram_id')?.[1]
  if (tgId) return `ID Telegram: ${tgId}`
  return formatPairs(pairs)
}

function formatSystemUpdate(raw: string): string {
  const pairs = parseDetailPairs(raw)
  const taskId = pairs.find(([key]) => key === 'task_id')?.[1]
  if (taskId) return `Задача №${taskId}`
  return formatPairs(pairs)
}

function formatVpnPublish(raw: string): string {
  const pairs = parseDetailPairs(raw)
  if (!pairs.length) return raw
  return pairs
    .map(([key, value]) => {
      if (key === 'mode') return `Режим: ${value}`
      if (key === 'port') return `Порт: ${value}`
      return `${translateKey(key)}: ${value}`
    })
    .join('; ')
}

function formatEditFilesTransfer(raw: string): string {
  const pairs = parseDetailPairs(raw.replace(/;/g, '; '))
  const byKey = new Map(pairs)
  const parts: string[] = []
  if (byKey.get('from')) parts.push(`Из узла «${byKey.get('from')}»`)
  if (byKey.get('files')) parts.push(`Файлы: ${byKey.get('files')}`)
  if (byKey.get('success') !== undefined) parts.push(`Успешно: ${byKey.get('success')}`)
  if (byKey.get('failed') !== undefined) parts.push(`Ошибки: ${byKey.get('failed')}`)
  if (byKey.get('doall')) {
    parts.push(byKey.get('doall') === 'true' ? 'С doall' : 'Без doall')
  }
  return parts.join('; ') || formatPairs(pairs)
}

function formatMonitorSettings(raw: string): string {
  const pairs = parseDetailPairs(raw)
  return pairs
    .map(([key, value]) => {
      if (key === 'cpu') return `CPU: ${value}`
      if (key === 'ram') return `RAM: ${value}`
      if (key === 'interval') return `Интервал: ${value}`
      if (key === 'cooldown') return `Пауза: ${value}`
      if (key === 'sustained') return `Устойчивость: ${value}`
      return `${translateKey(key)}: ${value}`
    })
    .join('; ')
}

function formatSecuritySettings(raw: string): string {
  if (raw === 'no-op') return 'Без изменений'
  return raw
    .split(', ')
    .map((field) => SECURITY_FIELD_LABELS[field] ?? field.replace(/_/g, ' '))
    .join(', ')
}

function formatBotSettings(raw: string): string {
  const pairs = parseDetailPairs(raw)
  const byKey = new Map(pairs)
  const parts: string[] = []
  if (byKey.get('source') === 'telegram_bot') {
    parts.push('Через Telegram-бот')
  }
  if (byKey.get('field')) {
    const field = byKey.get('field') ?? ''
    const fieldLabel = SECURITY_FIELD_LABELS[field] ?? field.replace(/^event:/, 'событие ').replace(/_/g, ' ')
    parts.push(`Поле: ${fieldLabel}`)
  }
  if (byKey.get('value')) {
    parts.push(`Значение: ${translateValue('value', byKey.get('value') ?? '')}`)
  }
  if (byKey.get('action')) {
    parts.push(`Действие: ${translateValue('action', byKey.get('action') ?? '')}`)
  }
  if (parts.length) return parts.join('; ')
  return formatPairs(pairs)
}

function formatHaReplicateFailure(raw: string): string {
  const pairs = parseDetailPairs(raw.replace(/,\s+(?=[a-z_]+=)/gi, '; '))
  return formatPairs(pairs)
}

function formatCidrProvider(raw: string): string {
  const match = raw.match(/^(.+?):\s*\+(\d+)\s*cidr,\s*\+(\d+)\s*asn$/i)
  if (!match) return raw
  return `Провайдер ${match[1]}: +${match[2]} CIDR, +${match[3]} ASN`
}

function formatGeneric(raw: string): string {
  const arrow = formatArrowChange(raw)
  if (arrow) return arrow

  const known = DETAIL_VALUE_LABELS[raw] ?? DETAIL_VALUE_LABELS[raw.toLowerCase()]
  if (known) return known

  const pairs = parseDetailPairs(raw)
  if (pairs.length) return formatPairs(pairs)

  const clientDays = formatClientDays(raw)
  if (clientDays) return clientDays

  const disconnect = formatDisconnect(raw)
  if (disconnect) return disconnect

  const traffic = formatTrafficLimit(raw)
  if (traffic) return traffic

  return raw
}

/** Человекочитаемые русские детали для журнала действий. */
export function actionLogDetailsLabel(action: string, details?: string | null): string | null {
  const raw = (details ?? '').trim()
  if (!raw) {
    if (action === 'login_success') return 'Способ входа: пароль'
    return null
  }

  switch (action) {
    case 'login_success':
      return formatLoginSuccess(raw)
    case 'login_failed':
      return raw === 'invalid credentials' ? 'Неверный логин или пароль' : formatGeneric(raw)
    case 'passkey_login_failed':
      return 'Не удалось войти по passkey'
    case 'passkey_register':
      return `Устройство: ${raw}`
    case 'passkey_delete':
      return 'Удалён ключ доступа'
    case 'telegram_link':
      return formatTelegramLink(raw)
    case 'user_create':
      return formatUserCreate(raw)
    case 'user_update':
      return raw.startsWith('target=') ? `Пользователь: ${raw.slice('target='.length)}` : formatGeneric(raw)
    case 'user_delete':
      return raw.startsWith('deleted=') ? `Удалён: ${raw.slice('deleted='.length)}` : formatGeneric(raw)
    case 'settings_cidr_deploy':
      return formatCidrDeployTarget(raw)
    case 'settings_cidr_rollback_queued':
      return raw ? `Метка бэкапа: ${raw}` : null
    case 'settings_cidr_custom_provider':
      return formatCidrProvider(raw)
    case 'system_update_queued':
    case 'system_rebuild_queued':
      return formatSystemUpdate(raw)
    case 'settings_vpn_network_publish':
      return formatVpnPublish(raw)
    case 'node_create':
    case 'node_update':
    case 'node_delete':
    case 'node_activate':
      return formatNodeRef(raw) ?? formatGeneric(raw)
    case 'node_update_apply':
    case 'node_restart_agent':
      return raw.startsWith('node=') ? `Узел: ${raw.slice('node='.length)}` : formatGeneric(raw)
    case 'node_update_roll_queued':
      return raw.startsWith('nodes=') ? `Узлы: ${raw.slice('nodes='.length)}` : formatGeneric(raw)
    case 'openvpn_temp_block':
    case 'wg_temp_block':
    case 'wg_set_expiry':
      return formatClientDays(raw) ?? formatGeneric(raw)
    case 'openvpn_perm_block':
    case 'openvpn_unblock':
    case 'wg_perm_block':
    case 'wg_unblock':
    case 'openvpn_traffic_limit_clear':
    case 'wg_traffic_limit_clear':
      return `Клиент: ${raw}`
    case 'openvpn_disconnect':
      return formatDisconnect(raw) ?? formatGeneric(raw)
    case 'openvpn_traffic_limit_set':
    case 'wg_traffic_limit_set':
      return formatTrafficLimit(raw) ?? formatGeneric(raw)
    case 'security_settings_update':
      return formatSecuritySettings(raw)
    case 'settings_public_download_toggle':
      return formatArrowChange(raw) ?? `Публичное скачивание: ${raw}`
    case 'security_temp_whitelist':
    case 'settings_security_temp_whitelist':
      return formatGeneric(raw)
    case 'security_temp_whitelist_remove':
    case 'settings_security_temp_whitelist_remove':
    case 'settings_security_unban':
      return raw.startsWith('ip=') ? `IP: ${raw.slice('ip='.length)}` : formatGeneric(raw)
    case 'settings_monitor_update':
      return formatMonitorSettings(raw)
    case 'edit_files_transfer':
      return formatEditFilesTransfer(raw)
    case 'ha_replicate_partial_failure':
      return formatHaReplicateFailure(raw)
    case 'config_download':
      return formatGeneric(raw)
    case 'backup_restore':
      return raw.startsWith('file=') ? `Архив: ${raw.slice('file='.length)}` : `Архив: ${raw}`
    case 'secrets_rotation_apply':
      return raw.startsWith('secret_id=') ? `Секрет: ${raw.slice('secret_id='.length)}` : formatGeneric(raw)
    case 'audit_stream_test':
      return 'Тестовое событие отправлено'
    case 'event_webhook_settings_update':
      return 'Обновлены настройки webhook'
    case 'audit_stream_settings_update':
      return 'Обновлены настройки потока аудита'
    default:
      if (raw.includes('source=telegram_bot') || raw.startsWith('field=')) {
        return formatBotSettings(raw)
      }
      return formatGeneric(raw)
  }
}
