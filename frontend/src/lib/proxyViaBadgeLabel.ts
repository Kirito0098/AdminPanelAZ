/** Подпись рядом с адресом клиента в NOC при via_proxy. */
export function formatProxyViaBadgeLabel(proxyResolved?: boolean): string {
  if (proxyResolved) return 'через прокси'
  return 'через прокси · IP не восстановлен'
}
