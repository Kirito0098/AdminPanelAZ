import type { BackgroundTask } from '@/types'

type HaHostCopy = {
  node_name?: string
  node_id?: number
  hosts?: Record<string, string>
  error?: string
}

type HaOpenVpnRestart = {
  node_name?: string
  node_id?: number
  restarted?: string[]
  skipped?: string[]
  failed?: Array<{ unit?: string; error?: string }>
}

type HaOpenVpnProfileCopy = {
  node_name?: string
  node_id?: number
  success?: boolean
  error?: string
}

type HaReplicaPrune = {
  node_name?: string
  node_id?: number
  removed_ovpn?: string[]
  removed_wg?: string[]
  errors?: string[]
  success?: boolean
}

type HaPushFullPayload = {
  host_copy?: HaHostCopy[]
  restored?: Array<{ node_name?: string; node_id?: number }>
  openvpn_restart?: HaOpenVpnRestart[]
  openvpn_profile_copy?: HaOpenVpnProfileCopy[]
  replica_prune?: HaReplicaPrune[]
  message?: string
}

type HaSharedDomainPayload = {
  domain?: string
  updated?: Array<{ node_name?: string; node_id?: number }>
  openvpn_restart?: HaOpenVpnRestart[]
}

type HaSetupPayload = {
  shared_domain?: HaSharedDomainPayload
  push_full?: HaPushFullPayload
}

export type HaSyncResultVariant = 'success' | 'warning' | 'error'
export type HaSyncItemStatus = 'success' | 'warning' | 'error' | 'skipped'

export interface HaSyncResultItem {
  nodeName: string
  text: string
  explanation?: string
  status: HaSyncItemStatus
  details?: string[]
}

export interface HaSyncResultSection {
  title: string
  description?: string
  items: HaSyncResultItem[]
}

export interface HaSyncResultView {
  title: string
  description?: string
  variant: HaSyncResultVariant
  sections: HaSyncResultSection[]
}

const HOST_LABELS: Record<string, string> = {
  openvpn_host: 'Домен в .ovpn-конфигах (OpenVPN)',
  wireguard_host: 'Домен в .conf-конфигах (WireGuard)',
  OPENVPN_HOST: 'Домен в .ovpn-конфигах (OpenVPN)',
  WIREGUARD_HOST: 'Домен в .conf-конфигах (WireGuard)',
}

const OPENVPN_UNIT_LABELS: Record<string, string> = {
  'openvpn-server@antizapret-udp': 'AntiZapret UDP',
  'openvpn-server@antizapret-tcp': 'AntiZapret TCP',
  'openvpn-server@vpn-udp': 'VPN UDP',
  'openvpn-server@vpn-tcp': 'VPN TCP',
}

function nodeLabel(item: { node_name?: string; node_id?: number }): string {
  return item.node_name || String(item.node_id ?? 'узел')
}

function formatHostEntry(key: string, value: string): string {
  const label = HOST_LABELS[key] || key
  return `${label}: ${value}`
}

function formatOpenVpnUnit(unit: string): string {
  const label = OPENVPN_UNIT_LABELS[unit] || unit.replace('openvpn-server@', '')
  return label
}

function parseTaskOutput(task: BackgroundTask | null | undefined): unknown {
  const raw = task?.output
  if (!raw) return null
  try {
    return JSON.parse(raw) as unknown
  } catch {
    return null
  }
}

function buildOpenVpnProfileCopySection(
  items: HaOpenVpnProfileCopy[] | undefined,
): HaSyncResultSection | null {
  if (!items?.length) return null
  return {
    title: 'OpenVPN-профили на реплике',
    description:
      'После restore с primary на реплику скопированы те же .ovpn-файлы — один конфиг и один сертификат работают на обоих IP.',
    items: items.map((item) => {
      const name = nodeLabel(item)
      if (item.error) {
        return {
          nodeName: name,
          text: 'Не удалось скопировать .ovpn с primary',
          explanation: 'Replica может отклонять тот же сертификат, что принимает primary — повторите Push full.',
          status: 'error' as const,
          details: [item.error],
        }
      }
      return {
        nodeName: name,
        text: 'Профили OpenVPN совпадают с primary',
        explanation: 'Сертификаты в .ovpn не перевыпускались — только байт-копия с основного узла.',
        status: 'success' as const,
      }
    }),
  }
}

function buildHostCopySection(items: HaHostCopy[] | undefined): HaSyncResultSection | null {
  if (!items?.length) return null
  return {
    title: 'Адреса в конфигах клиентов',
    description:
      'На реплику скопированы те же домены, что и на основном узле. Их увидят пользователи в выданных .ovpn и WireGuard-конфигах.',
    items: items.map((item) => {
      const name = nodeLabel(item)
      if (item.error) {
        return {
          nodeName: name,
          text: 'Не удалось записать домены на реплику',
          explanation: 'Без совпадения хостов клиенты после переключения DNS подключатся не туда.',
          status: 'error' as const,
          details: [item.error],
        }
      }
      const hosts = item.hosts ?? {}
      const labels = Object.entries(hosts).map(([key, value]) => formatHostEntry(key, value))
      return {
        nodeName: name,
        text: labels.length ? 'Домены совпадают с основным узлом' : 'Параметры хостов обновлены',
        explanation: 'Реплика будет выдавать конфиги с тем же адресом подключения.',
        status: 'success' as const,
        details: labels.length ? labels : undefined,
      }
    }),
  }
}

function buildOpenVpnSection(
  items: HaOpenVpnRestart[] | undefined,
  context: 'domain' | 'replica',
): HaSyncResultSection | null {
  if (!items?.length) return null
  const sectionDescription =
    context === 'domain'
      ? 'После смены домена перезапущены службы OpenVPN, чтобы новые параметры из setup применились к работающим туннелям.'
      : 'После восстановления бэкапа перезапущены службы OpenVPN на реплике — иначе она могла бы работать со старыми сертификатами или портами.'

  return {
    title: 'Перезапуск OpenVPN',
    description: sectionDescription,
    items: items.flatMap((item) => {
      const name = nodeLabel(item)
      const result: HaSyncResultItem[] = []
      if (item.restarted?.length) {
        result.push({
          nodeName: name,
          text: `Перезапущено служб: ${item.restarted.length}`,
          explanation: 'Службы снова читают актуальные настройки и сертификаты с диска.',
          status: 'success',
          details: item.restarted.map((unit) => formatOpenVpnUnit(unit)),
        })
      }
      if (item.failed?.length) {
        result.push({
          nodeName: name,
          text: 'Часть служб OpenVPN не перезапустилась',
          explanation: 'Проверьте journalctl на узле — клиенты этих профилей могут не подключаться.',
          status: 'error',
          details: item.failed.map(
            (entry) =>
              `${formatOpenVpnUnit(entry.unit || 'openvpn')}: ${entry.error || 'неизвестная ошибка'}`,
          ),
        })
      }
      if (!item.restarted?.length && !item.failed?.length && item.skipped?.length) {
        result.push({
          nodeName: name,
          text: 'Профили OpenVPN на этом узле не установлены',
          explanation: 'Это нормально, если на сервере не развёрнут соответствующий профиль.',
          status: 'skipped',
          details: item.skipped.map((unit) => formatOpenVpnUnit(unit)),
        })
      }
      return result
    }),
  }
}

function buildRestoredSection(items: HaPushFullPayload['restored']): HaSyncResultSection | null {
  if (!items?.length) return null
  return {
    title: 'Копия состояния AntiZapret',
    description:
      'VPN/crypto на реплике заменены содержимым с primary (wipe-and-replace): PKI OpenVPN, ключи WireGuard и профили клиентов. Каталог config/ по-прежнему merge; без client.sh 7 на реплике.',
    items: items.map((item) => ({
      nodeName: nodeLabel(item),
      text: 'VPN/crypto на реплике совпадает с основным узлом',
      explanation: 'Лишние сертификаты и файлы на реплике удалены перед копированием — не merge поверх старого состояния.',
      status: 'success' as const,
    })),
  }
}

function buildReplicaPruneSection(items: HaReplicaPrune[] | undefined): HaSyncResultSection | null {
  if (!items?.length) return null
  return {
    title: 'Очистка лишних VPN-клиентов на replica',
    description:
      'Клиенты OpenVPN и WireGuard, которых нет на primary, удалены с диска и из runtime реплики — чтобы Verify не показывал only_replica.',
    items: items.map((item) => {
      const name = nodeLabel(item)
      const removedOvpn = item.removed_ovpn ?? []
      const removedWg = item.removed_wg ?? []
      const errors = item.errors ?? []
      const details: string[] = []
      if (removedOvpn.length) {
        details.push(`OpenVPN: ${removedOvpn.join(', ')}`)
      }
      if (removedWg.length) {
        details.push(`WireGuard: ${removedWg.join(', ')}`)
      }
      if (errors.length) {
        details.push(...errors.map((entry) => `Ошибка: ${entry}`))
      }
      if (errors.length) {
        return {
          nodeName: name,
          text: 'Не все лишние клиенты удалены',
          explanation: 'На реплике могут остаться сертификаты или peers, которых нет на primary — повторите Push full.',
          status: 'error' as const,
          details: details.length ? details : undefined,
        }
      }
      if (!removedOvpn.length && !removedWg.length) {
        return {
          nodeName: name,
          text: 'Лишних VPN-клиентов не было',
          explanation: 'Состав клиентов на реплике уже совпадал с primary.',
          status: 'skipped' as const,
        }
      }
      return {
        nodeName: name,
        text: `Удалено клиентов: OpenVPN ${removedOvpn.length}, WireGuard ${removedWg.length}`,
        explanation: 'После очистки реплика содержит только тех VPN-клиентов, что есть на основном узле.',
        status: 'success' as const,
        details: details.length ? details : undefined,
      }
    }),
  }
}

function buildDomainSection(
  items: HaSharedDomainPayload['updated'],
  domain?: string,
): HaSyncResultSection | null {
  if (!items?.length) return null
  const domainHint = domain ? ` (${domain})` : ''
  return {
    title: 'Общий домен в setup',
    description: `В файл setup на каждом узле записан домен${domainHint} для OPENVPN_HOST и WIREGUARD_HOST — от него зависят адреса в новых конфигах.`,
    items: items.map((item) => ({
      nodeName: nodeLabel(item),
      text: domain ? `В setup записан домен ${domain}` : 'Домен записан в setup',
      explanation: 'Далее на узле выполняются doall.sh и client.sh 7 — применяют домен к конфигам и профилям.',
      status: 'success' as const,
      details: domain
        ? [
            formatHostEntry('openvpn_host', domain),
            formatHostEntry('wireguard_host', domain),
          ]
        : undefined,
    })),
  }
}

function countSectionStats(sections: HaSyncResultSection[]) {
  let ok = 0
  let warn = 0
  let err = 0
  for (const section of sections) {
    for (const item of section.items) {
      if (item.status === 'success') ok += 1
      else if (item.status === 'error') err += 1
      else warn += 1
    }
  }
  return { ok, warn, err }
}

function buildOverviewDescription(
  sections: HaSyncResultSection[],
  domain?: string,
  mode?: 'setup' | 'domain' | 'push',
): string {
  const { ok, warn, err } = countSectionStats(sections)
  const parts: string[] = []

  if (mode === 'setup') {
    parts.push(
      domain
        ? `Полная настройка HA для ${domain}: домен на всех узлах, копия AntiZapret на реплику, перезапуск OpenVPN.`
        : 'Полная настройка HA: домен, копия на реплику, перезапуск OpenVPN.',
    )
  } else if (mode === 'domain') {
    parts.push(
      domain
        ? `Домен ${domain} применён на всех узлах группы (setup → doall.sh → client.sh 7).`
        : 'Домен применён на всех узлах группы.',
    )
  } else if (mode === 'push') {
    parts.push(
      'Полная синхронизация: VPN/crypto на реплике заменены бэкапом с primary; лишние клиенты удалены.',
    )
  }

  const stats: string[] = []
  if (ok) stats.push(`успешно: ${ok}`)
  if (warn) stats.push(`пропущено: ${warn}`)
  if (err) stats.push(`ошибок: ${err}`)
  if (stats.length) parts.push(`Операций — ${stats.join(', ')}.`)

  if (err) {
    parts.push('Исправьте ошибки и повторите синхронизацию.')
  } else if (warn && !err) {
    parts.push('Предупреждения обычно безопасны (например, неустановленный профиль OpenVPN).')
  } else {
    parts.push('Рекомендуется нажать «Проверить» и затем настроить DNS failover.')
  }

  return parts.join(' ')
}

function resolveVariant(sections: HaSyncResultSection[], task?: BackgroundTask | null): HaSyncResultVariant {
  if (task?.status === 'failed') return 'error'
  const hasError = sections.some((section) =>
    section.items.some((item) => item.status === 'error'),
  )
  if (hasError) return 'warning'
  const hasWarning = sections.some((section) =>
    section.items.some((item) => item.status === 'warning'),
  )
  if (hasWarning) return 'warning'
  return 'success'
}

function pushSection(sections: HaSyncResultSection[], section: HaSyncResultSection | null) {
  if (section?.items.length) sections.push(section)
}

export function parseHaSyncTaskResult(
  task: BackgroundTask | null | undefined,
): HaSyncResultView | null {
  const parsed = parseTaskOutput(task)
  const sections: HaSyncResultSection[] = []
  let title = task?.message?.trim() || 'Синхронизация завершена'
  let mode: 'setup' | 'domain' | 'push' | undefined
  let domain: string | undefined

  if (parsed && typeof parsed === 'object') {
    if ('shared_domain' in parsed || 'push_full' in parsed) {
      const setup = parsed as HaSetupPayload
      domain = setup.shared_domain?.domain
      const hasPush = Boolean(setup.push_full)
      const hasDomain = Boolean(setup.shared_domain)

      if (hasDomain && hasPush) {
        mode = 'setup'
        title = domain ? `HA-группа настроена: ${domain}` : 'HA-группа настроена'
      } else if (hasDomain) {
        mode = 'domain'
        title = domain ? `Домен ${domain} применён` : 'Домен применён на узлах'
      } else if (hasPush) {
        mode = 'push'
        title = 'Полная синхронизация завершена'
      }

      pushSection(sections, buildDomainSection(setup.shared_domain?.updated, domain))
      pushSection(sections, buildOpenVpnSection(setup.shared_domain?.openvpn_restart, 'domain'))
      pushSection(sections, buildHostCopySection(setup.push_full?.host_copy))
      pushSection(sections, buildRestoredSection(setup.push_full?.restored))
      pushSection(sections, buildOpenVpnProfileCopySection(setup.push_full?.openvpn_profile_copy))
      pushSection(sections, buildReplicaPruneSection(setup.push_full?.replica_prune))
      pushSection(sections, buildOpenVpnSection(setup.push_full?.openvpn_restart, 'replica'))
    } else if ('host_copy' in parsed || 'restored' in parsed) {
      const push = parsed as HaPushFullPayload
      mode = 'push'
      title = 'Полная синхронизация завершена'
      pushSection(sections, buildHostCopySection(push.host_copy))
      pushSection(sections, buildRestoredSection(push.restored))
      pushSection(sections, buildOpenVpnProfileCopySection(push.openvpn_profile_copy))
      pushSection(sections, buildReplicaPruneSection(push.replica_prune))
      pushSection(sections, buildOpenVpnSection(push.openvpn_restart, 'replica'))
    } else if ('updated' in parsed || 'domain' in parsed) {
      const domainPayload = parsed as HaSharedDomainPayload
      domain = domainPayload.domain
      mode = 'domain'
      title = domain ? `Домен ${domain} применён` : 'Домен применён на узлах'
      pushSection(sections, buildDomainSection(domainPayload.updated, domain))
      pushSection(sections, buildOpenVpnSection(domainPayload.openvpn_restart, 'domain'))
    }
  }

  if (!sections.length) {
    if (!task?.message?.trim()) return null
    return {
      title,
      description: task.message.trim(),
      variant: task.status === 'failed' ? 'error' : 'success',
      sections: [],
    }
  }

  const description = buildOverviewDescription(sections, domain, mode)

  return {
    title,
    description,
    variant: resolveVariant(sections, task),
    sections,
  }
}

export function formatHaSyncTaskSummary(task: BackgroundTask | null | undefined): string | null {
  return parseHaSyncTaskResult(task)?.title ?? task?.message?.trim() ?? null
}

export function formatHaSyncTaskDetails(task: BackgroundTask | null | undefined): string[] {
  const result = parseHaSyncTaskResult(task)
  if (!result) return []
  return result.sections.flatMap((section) =>
    section.items.map((item) => {
      const details = item.details?.length ? ` — ${item.details.join('; ')}` : ''
      return `${item.nodeName}: ${item.text}${details}`
    }),
  )
}
