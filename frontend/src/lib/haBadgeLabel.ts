/** Склонение «N узел/узла/узлов» для русского UI. */
export function formatHaNodeCount(count: number): string {
  const n = Math.abs(count) % 100
  const n1 = n % 10
  if (n > 10 && n < 20) return `${count} узлов`
  if (n1 === 1) return `${count} узел`
  if (n1 >= 2 && n1 <= 4) return `${count} узла`
  return `${count} узлов`
}

export function formatHaBadgeLabel(ha: { shared_domain: string; node_count: number }): string {
  return `HA: ${ha.shared_domain} · ${formatHaNodeCount(ha.node_count)}`
}

export function haBadgeTitle(ha: { node_count: number }): string {
  return `Клиент синхронизирован в HA-группе и доступен на ${formatHaNodeCount(ha.node_count)} (primary и replica)`
}
