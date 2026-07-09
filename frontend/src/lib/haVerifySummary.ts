import type { NodeSyncMismatch, NodeSyncVerifyResult } from '@/types'

export type HaVerifyResultVariant = 'success' | 'warning'

export interface HaVerifyMismatchView {
  title: string
  details: string[]
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
  replicas: HaVerifyReplicaView[]
  nextStep?: string
}

const VERIFY_CHECKS = [
  'доступность узлов (online)',
  'список клиентов OpenVPN',
  'список клиентов WireGuard',
  'сертификаты PKI и файлы WireGuard',
  'файлы настроек AntiZapret (config/)',
] as const

const FINGERPRINT_LABELS: Record<string, string> = {
  'easyrsa3/pki/ca.crt': 'Корневой сертификат CA (OpenVPN)',
  'easyrsa3/pki/index.txt': 'Реестр выданных сертификатов',
  'easyrsa3/pki/serial': 'Счётчик серийных номеров PKI',
  'wireguard/conf_files': 'Конфигурации WireGuard (/etc/wireguard/*.conf)',
  'antizapret/config': 'Файлы настроек AntiZapret (config/)',
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
    const details = [`Сравниваемый объект: ${label}`]
    if (mismatch.primary || mismatch.replica) {
      details.push(`Хеш на основном: ${shortHash(mismatch.primary)}`)
      details.push(`Хеш на реплике: ${shortHash(mismatch.replica)}`)
    }
    const hint =
      path.startsWith('easyrsa3/') || path === 'wireguard/conf_files'
        ? 'Скорее всего реплика отстаёт от основного — нажмите «Синхронизировать» (копирует PKI и WireGuard).'
        : 'Файлы config/ различаются — проверьте правки на основном узле или выполните синхронизацию.'
    return { title: 'Разное содержимое файлов', details, hint }
  }

  return {
    title: mismatch.kind || 'Расхождение',
    details: [mismatch.detail || 'Обнаружено отличие между основным узлом и репликой.'],
    hint: 'Выполните «Синхронизировать» или устраните отличие вручную на основном узле.',
  }
}

export function parseHaVerifyResult(
  result: NodeSyncVerifyResult,
  groupName?: string,
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
  if (result.ready) {
    nextStep = 'Настройте DNS: A-записи домена на IP всех узлов и health-check у провайдера (кнопка «Настройка DNS»).'
  } else if (offlineReplicas.length) {
    nextStep = `Сначала восстановите связь с ${offlineReplicas.join(', ')}, затем повторите проверку.`
  } else if (mismatchCount) {
    nextStep = 'Нажмите «Синхронизировать» для выравнивания реплики с основным узлом.'
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
    replicas,
    nextStep,
  }
}
