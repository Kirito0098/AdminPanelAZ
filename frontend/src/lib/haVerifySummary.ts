import type { NodeSyncMismatch, NodeSyncVerifyResult } from '@/types'

export type HaVerifyResultVariant = 'success' | 'warning'

export interface HaVerifyFileEntry {
  filename: string
  title?: string
}

export interface HaVerifyFileGroup {
  label: string
  files: HaVerifyFileEntry[]
}

export interface HaVerifyMismatchView {
  title: string
  details: string[]
  fileGroups?: HaVerifyFileGroup[]
  hint?: string
}

export interface HaVerifyReplicaView {
  nodeName: string
  online: boolean
  ok: boolean
  summary: string
  checkedItems?: string[]
  mismatches: HaVerifyMismatchView[]
}

export interface HaVerifyResultView {
  title: string
  description: string
  variant: HaVerifyResultVariant
  groupName?: string
  domain: string
  checkedSummary: string[]
  primaryProfileIssues?: HaVerifyMismatchView[]
  replicas: HaVerifyReplicaView[]
  nextStep?: string
}

const VERIFY_CHECKS = [
  'доступность узлов (online)',
  'список клиентов OpenVPN',
  'список клиентов WireGuard',
  'сертификаты PKI и файлы WireGuard',
  'сертификаты в файлах .ovpn (не отозваны)',
  'файлы настроек AntiZapret (config/)',
] as const

const PROFILE_CERT_STATUS_LABELS: Record<string, string> = {
  revoked: 'отозван',
  expired: 'истёк',
  unknown_serial: 'не удалось прочитать serial',
  missing_cert: 'нет блока <cert>',
  not_in_index: 'нет в реестре PKI',
}

const FINGERPRINT_LABELS: Record<string, string> = {
  'easyrsa3/pki/ca.crt': 'Корневой сертификат CA (OpenVPN)',
  'easyrsa3/pki/crl.pem': 'Список отозванных сертификатов (CRL)',
  'easyrsa3/pki/index.txt': 'Реестр выданных сертификатов',
  'easyrsa3/pki/serial': 'Счётчик серийных номеров PKI',
  'wireguard/conf_files': 'Конфигурации WireGuard (/etc/wireguard/*.conf)',
  'openvpn/client_profiles': 'Файлы профилей OpenVPN (.ovpn)',
  'antizapret/config': 'Файлы настроек AntiZapret (config/)',
}

const CONFIG_FILE_TITLES: Record<string, string> = {
  'include-hosts.txt': 'Включить домены',
  'exclude-hosts.txt': 'Исключить домены',
  'include-ips.txt': 'Включить IP/CIDR',
  'exclude-ips.txt': 'Исключить IP/CIDR',
  'allow-ips.txt': 'Разрешённые IP',
  'drop-ips.txt': 'Блокировать IP',
  'forward-ips.txt': 'Перенаправлять IP',
  'include-adblock-hosts.txt': 'Adblock — включить',
  'exclude-adblock-hosts.txt': 'Adblock — исключить',
  'remove-hosts.txt': 'Удалить домены',
  'deny-ips.txt': 'Запретить входящие IP',
}

function formatConfigFileEntry(filename: string): HaVerifyFileEntry {
  return { filename, title: CONFIG_FILE_TITLES[filename] }
}

function categorizeConfigFileEntries(files: string[]): HaVerifyFileGroup[] {
  const providers: HaVerifyFileEntry[] = []
  const routing: HaVerifyFileEntry[] = []
  const other: HaVerifyFileEntry[] = []

  for (const filename of [...files].sort()) {
    const entry = formatConfigFileEntry(filename)
    if (filename.startsWith('AP-') || filename.startsWith('AZ-')) {
      providers.push(entry)
    } else if (CONFIG_FILE_TITLES[filename]) {
      routing.push(entry)
    } else {
      other.push(entry)
    }
  }

  const groups: HaVerifyFileGroup[] = []
  if (providers.length) {
    groups.push({ label: 'Файлы провайдеров (CIDR)', files: providers })
  }
  if (routing.length) {
    groups.push({ label: 'Списки маршрутизации', files: routing })
  }
  if (other.length) {
    groups.push({ label: 'Прочие файлы', files: other })
  }
  return groups
}

function appendFileDiffGroups(
  groups: HaVerifyFileGroup[],
  prefix: string,
  files: string[],
): void {
  const categorized = categorizeConfigFileEntries(files)
  if (categorized.length > 1) {
    for (const group of categorized) {
      groups.push({
        label: `${prefix} — ${group.label} (${group.files.length})`,
        files: group.files,
      })
    }
    return
  }
  groups.push({
    label: `${prefix} (${files.length})`,
    files: files.map(formatConfigFileEntry),
  })
}

function buildConfigFileGroups(
  changed: string[] | undefined,
  onlyPrimary: string[] | undefined,
  onlyReplica: string[] | undefined,
): HaVerifyFileGroup[] {
  const groups: HaVerifyFileGroup[] = []
  if (changed?.length) {
    appendFileDiffGroups(groups, 'Отличается содержимое', changed)
  }
  if (onlyPrimary?.length) {
    appendFileDiffGroups(groups, 'Только на основном', onlyPrimary)
  }
  if (onlyReplica?.length) {
    appendFileDiffGroups(groups, 'Только на реплике', onlyReplica)
  }
  return groups
}

function shortHash(value?: string | null): string {
  if (!value) return '—'
  if (value.length <= 12) return value
  return `${value.slice(0, 8)}…${value.slice(-4)}`
}

export function formatVerifyMismatch(mismatch: NodeSyncMismatch): HaVerifyMismatchView {
  if (mismatch.kind === 'node_status') {
    return {
      title: 'Узел недоступен',
      details: [
        mismatch.detail || 'Панель не может связаться с репликой или узел помечен как offline.',
      ],
      hint: 'Откройте «Узлы» → проверьте статус, host, порт и API-ключ. После восстановления связи нажмите «Проверить» снова.',
    }
  }

  if (mismatch.kind === 'openvpn_clients') {
    const details: string[] = []
    if (mismatch.only_primary?.length) {
      details.push(
        `Есть только на основном (${mismatch.only_primary.length}): ${mismatch.only_primary.join(', ')}`,
      )
    }
    if (mismatch.only_replica?.length) {
      details.push(
        `Есть только на реплике (${mismatch.only_replica.length}): ${mismatch.only_replica.join(', ')}`,
      )
    }
    return {
      title: 'Разные клиенты OpenVPN',
      details: details.length ? details : ['Наборы имён клиентов на узлах не совпадают.'],
      hint: 'Создайте или удалите клиентов на основном узле и дождитесь авто-синхронизации, либо нажмите «Синхронизировать» для полного выравнивания.',
    }
  }

  if (mismatch.kind === 'openvpn_profile_certs') {
    const issues = mismatch.issues ?? []
    const details = issues.map(
      (issue) =>
        `${issue.client_name}: ${issue.filename} — сертификат ${PROFILE_CERT_STATUS_LABELS[issue.status] || issue.status}${
          issue.serial_hex ? ` (${issue.serial_hex})` : ''
        }`,
    )
    return {
      title: 'Недействительный сертификат в .ovpn',
      details: details.length ? details : ['В профиле OpenVPN встроен отозванный или просроченный сертификат.'],
      hint: 'Нажмите «Синхронизировать» — PKI и .ovpn будут скопированы с primary на replica без перевыпуска сертификатов.',
    }
  }

  if (mismatch.kind === 'wireguard_clients') {
    const details: string[] = []
    if (mismatch.only_primary?.length) {
      details.push(
        `Есть только на основном (${mismatch.only_primary.length}): ${mismatch.only_primary.join(', ')}`,
      )
    }
    if (mismatch.only_replica?.length) {
      details.push(
        `Есть только на реплике (${mismatch.only_replica.length}): ${mismatch.only_replica.join(', ')}`,
      )
    }
    return {
      title: 'Разные клиенты WireGuard',
      details: details.length ? details : ['Наборы имён peer на узлах не совпадают.'],
      hint: 'Выровняйте клиентов через основной узел или выполните полную синхронизацию HA.',
    }
  }

  if (mismatch.kind === 'fingerprint') {
    const path = mismatch.path || ''
    const label = FINGERPRINT_LABELS[path] || path || 'Файлы на диске'
    const details: string[] = []

    if (path === 'antizapret/config') {
      const fileGroups = buildConfigFileGroups(
        mismatch.changed_files,
        mismatch.only_primary,
        mismatch.only_replica,
      )
      const hasFileDetails = fileGroups.length > 0
      if (mismatch.detail) {
        details.push(mismatch.detail)
      }
      if (hasFileDetails && (mismatch.primary || mismatch.replica)) {
        details.push(
          `Хеш каталога config/: основной ${shortHash(mismatch.primary)}, реплика ${shortHash(mismatch.replica)}`,
        )
      } else if (mismatch.primary || mismatch.replica) {
        details.push(`Хеш на основном: ${shortHash(mismatch.primary)}`)
        details.push(`Хеш на реплике: ${shortHash(mismatch.replica)}`)
      }

      const hint =
        'Файлы config/ различаются — проверьте правки на основном узле или выполните синхронизацию.'
      return {
        title: 'Разное содержимое файлов',
        details,
        fileGroups: hasFileDetails ? fileGroups : undefined,
        hint,
      }
    } else if (mismatch.primary || mismatch.replica) {
      details.push(`Сравниваемый объект: ${label}`)
      details.push(`Хеш на основном: ${shortHash(mismatch.primary)}`)
      details.push(`Хеш на реплике: ${shortHash(mismatch.replica)}`)
    } else {
      details.push(`Сравниваемый объект: ${label}`)
    }

    const hint =
      path.startsWith('easyrsa3/') || path === 'wireguard/conf_files' || path === 'openvpn/client_profiles'
        ? 'Скорее всего реплика отстаёт от основного — нажмите «Синхронизировать» (копирует PKI, .ovpn и WireGuard).'
        : 'Файлы config/ различаются — проверьте правки на основном узле или выполните синхронизацию.'
    return { title: 'Разное содержимое файлов', details, hint }
  }

  return {
    title: mismatch.kind || 'Расхождение',
    details: [mismatch.detail || 'Обнаружено отличие между основным узлом и репликой.'],
    hint: 'Выполните «Синхронизировать» или устраните отличие вручную на основном узле.',
  }
}

function formatPrimaryProfileIssues(
  issues: import('@/types').OpenVpnProfileCertIssue[] | undefined,
): HaVerifyMismatchView[] {
  if (!issues?.length) return []
  return [
    formatVerifyMismatch({
      kind: 'openvpn_profile_certs',
      issues,
    }),
  ]
}

export function parseHaVerifyResult(
  result: NodeSyncVerifyResult,
  groupName?: string,
  syncMode?: string,
): HaVerifyResultView {
  const replicas = (result.replicas ?? []).map((replica) => {
    const nodeName = replica.node_name || String(replica.node_id)
    const ok = replica.mismatches.length === 0

    return {
      nodeName,
      online: replica.online,
      ok,
      summary: ok
        ? 'Реплика совпадает с основным узлом по всем проверкам.'
        : `Найдено отличий: ${replica.mismatches.length}.`,
      checkedItems: ok ? [...VERIFY_CHECKS] : undefined,
      mismatches: replica.mismatches.map(formatVerifyMismatch),
    }
  })

  const mismatchCount = replicas.reduce((sum, replica) => sum + replica.mismatches.length, 0)
  const offlineReplicas = replicas.filter((replica) => !replica.online).map((replica) => replica.nodeName)

  let nextStep: string | undefined
  const manualMode = syncMode === 'manual_full'
  if (result.ready) {
    nextStep = 'Настройте DNS: A-записи домена на IP всех узлов и health-check у провайдера (кнопка «Настройка DNS»).'
  } else if (offlineReplicas.length) {
    nextStep = `Сначала восстановите связь с ${offlineReplicas.join(', ')}, затем повторите проверку.`
  } else if (mismatchCount) {
    nextStep = manualMode
      ? 'В режиме manual_full нажмите «Синхронизировать» для выравнивания реплики с основным узлом.'
      : 'Устраните отличия на primary (авто-синхронизация) или нажмите «Синхронизировать».'
  }

  const groupLabel = groupName ? `«${groupName}»` : `домен ${result.shared_domain}`

  return {
    title: result.ready ? 'Готово к DNS-переключению' : 'Есть расхождения',
    description: result.ready
      ? `Группа ${groupLabel}: основной узел и реплика совпадают. Failover по DNS можно включать.`
      : `Группа ${groupLabel}: между основным узлом и репликой есть ${mismatchCount} отличий. До переключения DNS это нужно устранить.`,
    variant: result.ready ? 'success' : 'warning',
    groupName,
    domain: result.shared_domain,
    checkedSummary: [...VERIFY_CHECKS],
    primaryProfileIssues: formatPrimaryProfileIssues(result.openvpn_profile_certs?.primary_issues),
    replicas,
    nextStep,
  }
}
