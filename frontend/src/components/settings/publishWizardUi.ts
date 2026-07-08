import type { VpnNetworkPublishMode, VpnNetworkSettings, VpnNetworkSslCertSuggestion } from '@/types'

type AlertVariant = 'info' | 'warning' | 'danger'

export interface PublishConfirmPlan {
  alertVariant: AlertVariant
  alertTitle: string
  bullets: string[]
  destructive: boolean
  accessUrl?: string
}

function domainHost(domain: string): string {
  return domain.trim().split(':')[0]
}

function hasLetsEncryptForDomain(settings: VpnNetworkSettings | null, domain: string): boolean {
  const host = domainHost(domain)
  if (!host) return false
  return Boolean(
    settings?.ssl_cert_suggestions?.some(
      (item) => item.source === 'letsencrypt' && item.cert.includes(`/live/${host}/`),
    ),
  )
}

function resolveDomainLetsEncrypt(
  settings: VpnNetworkSettings | null,
  domain: string,
  live: boolean | null | undefined,
): boolean {
  if (live != null) return live
  return hasLetsEncryptForDomain(settings, domain)
}

function filterWarningsForDomain(
  warnings: string[],
  settings: VpnNetworkSettings | null,
  domain: string,
): string[] {
  const host = domainHost(domain)
  if (!host) return warnings

  return warnings.filter((line) => {
    if (line.includes('уже есть Let') || line.includes("Let's Encrypt для") || line.includes('Сертификат Let')) {
      return hasLetsEncryptForDomain(settings, host)
    }
    if (
      line.includes('HSTS') ||
      line.includes('Nginx слушает') ||
      line.includes('Порт 443') ||
      line.includes('другой сайт')
    ) {
      const mentionsDomain = /[a-z0-9][a-z0-9.-]*\.[a-z]{2,}/i.test(line)
      if (mentionsDomain && !line.includes(host)) return false
    }
    return true
  })
}

export function guessPublishAccessUrl(
  mode: string,
  domain: string,
  backendPort: string,
  httpsPublicPort: string,
  settings: VpnNetworkSettings | null,
  domainLetsEncrypt?: boolean | null,
): string | undefined {
  const host = domainHost(domain)

  if (mode.startsWith('nginx_')) {
    if (!host) return undefined
    const port = Number(httpsPublicPort)
    return port === 443 ? `https://${host}/` : `https://${host}:${port}/`
  }

  if (mode.startsWith('uvicorn_')) {
    if (!host) return undefined
    const port = Number(backendPort)
    if (port !== 443 && resolveDomainLetsEncrypt(settings, domain, domainLetsEncrypt)) {
      return `https://${host}/`
    }
    return port === 443 ? `https://${host}/` : `https://${host}:${port}/`
  }

  if (mode === 'http_direct') {
    const accessHost = settings?.server_primary_ip?.trim()
    if (!accessHost) return undefined
    return `http://${accessHost}:${backendPort}/`
  }

  return undefined
}

export function filterPublishWarningsForMode(mode: string, warnings: string[]): string[] {
  if (mode.startsWith('nginx_') || mode === 'http_direct') {
    return []
  }

  if (mode === 'uvicorn_selfsigned') {
    return warnings.filter(
      (line) =>
        line.includes('HSTS') ||
        line.includes('443') ||
        line.includes('Nginx слушает') ||
        line.includes('другой сайт'),
    )
  }

  if (mode === 'uvicorn_le' || mode === 'uvicorn_custom') {
    return warnings.filter((line) => !line.includes('HSTS') && !line.includes('самоподпис'))
  }

  return warnings
}

export function buildPublishConfirmPlan(
  mode: string,
  modeInfo: VpnNetworkPublishMode,
  settings: VpnNetworkSettings | null,
  domain: string,
  backendPort: string,
  httpsPublicPort: string,
  domainLetsEncrypt?: boolean | null,
): PublishConfirmPlan {
  const host = domainHost(domain)
  const accessUrl = guessPublishAccessUrl(
    mode,
    domain,
    backendPort,
    httpsPublicPort,
    settings,
    domainLetsEncrypt,
  )
  const filteredWarnings = filterWarningsForDomain(
    filterPublishWarningsForMode(mode, settings?.uvicorn_publish_warnings ?? []),
    settings,
    domain,
  )

  if (mode === 'http_direct') {
    return {
      alertVariant: 'danger',
      alertTitle: 'Небезопасный режим',
      bullets: parsePublishModeWarning(modeInfo.warning).length
        ? parsePublishModeWarning(modeInfo.warning)
        : [
            'Панель будет доступна по HTTP без TLS — только для тестов.',
            'Включите ограничение по IP в разделе «Защита входа», если открываете в интернет.',
          ],
      destructive: true,
      accessUrl,
    }
  }

  if (mode.startsWith('nginx_')) {
    const bullets = [
      'Nginx будет принимать HTTPS снаружи, uvicorn — только на loopback.',
      'Панель перезапустится автоматически после применения.',
    ]
    if (mode === 'nginx_le' && resolveDomainLetsEncrypt(settings, domain, domainLetsEncrypt)) {
      bullets.unshift(`Сертификат Let's Encrypt для ${host || 'домена'} уже есть — будет переиспользован.`)
    }
    if (mode === 'nginx_custom' && resolveDomainLetsEncrypt(settings, domain, domainLetsEncrypt)) {
      bullets.unshift('Будут использованы указанные или найденные на сервере сертификаты.')
    }
    if (mode === 'nginx_selfsigned') {
      bullets.push(...parsePublishModeWarning(modeInfo.warning))
    }
    if (settings?.nginx_installed === false) {
      bullets.push('Nginx будет установлен, если ещё не установлен.')
    }
    return {
      alertVariant: mode === 'nginx_selfsigned' ? 'warning' : 'info',
      alertTitle: mode === 'nginx_selfsigned' ? 'Режим не рекомендуется для интернета' : 'Что будет настроено',
      bullets,
      destructive: false,
      accessUrl,
    }
  }

  if (mode.startsWith('uvicorn_')) {
    const bullets = [
      'TLS будет на uvicorn, без reverse proxy.',
      'Панель перезапустится автоматически.',
    ]
    if (accessUrl) {
      bullets.push(`Ожидаемый адрес: ${accessUrl}`)
    }
    if (mode === 'uvicorn_selfsigned') {
      bullets.push(...parsePublishModeWarning(modeInfo.warning))
    }
    if (filteredWarnings.length > 0) {
      bullets.push(...filteredWarnings)
    } else if (mode === 'uvicorn_le') {
      bullets.push('Если сертификата ещё нет — certbot попробует выпустить его без остановки других сайтов.')
    }

    const isRiskySelfSigned =
      mode === 'uvicorn_selfsigned' &&
      filteredWarnings.some((line) => line.includes('HSTS'))

    return {
      alertVariant: mode === 'uvicorn_selfsigned' ? 'danger' : filteredWarnings.length > 0 ? 'info' : 'info',
      alertTitle: publishUvicornWarningsTitle(mode, filteredWarnings),
      bullets,
      destructive: isRiskySelfSigned,
      accessUrl,
    }
  }

  return {
    alertVariant: 'warning',
    alertTitle: 'Изменение способа доступа',
    bullets: ['Сайт может быть недоступен несколько минут.'],
    destructive: false,
    accessUrl,
  }
}

export function inlinePublishWarnings(
  mode: string,
  settings: VpnNetworkSettings,
  domain = '',
): string[] {
  return filterWarningsForDomain(
    filterPublishWarningsForMode(mode, settings.uvicorn_publish_warnings ?? []),
    settings,
    domain,
  )
}

export function domainFromSslSuggestion(item: VpnNetworkSslCertSuggestion): string | null {
  const leMatch = item.cert.match(/\/letsencrypt\/live\/([^/]+)\//)
  if (leMatch?.[1]) return leMatch[1]
  const labelMatch = item.label.match(/\(([^)]+)\)\s*$/)
  if (labelMatch?.[1]) return labelMatch[1].trim().split(':')[0] || null
  return null
}

export function getLetsEncryptPathsForDomain(
  settings: VpnNetworkSettings | null,
  domain: string,
  liveStatus?: { has_letsencrypt: boolean; cert?: string | null; key?: string | null } | null,
): { cert: string; key: string } | null {
  if (liveStatus?.has_letsencrypt && liveStatus.cert && liveStatus.key) {
    return { cert: liveStatus.cert, key: liveStatus.key }
  }
  const host = domainHost(domain)
  if (!host) return null
  const match = settings?.ssl_cert_suggestions?.find(
    (item) => item.source === 'letsencrypt' && item.cert.includes(`/live/${host}/`),
  )
  if (!match) return null
  return { cert: match.cert, key: match.key }
}

export function hasLetsEncryptHint(
  settings: VpnNetworkSettings | null,
  domain = '',
  domainLetsEncrypt?: boolean | null,
): boolean {
  return resolveDomainLetsEncrypt(settings, domain, domainLetsEncrypt)
}

export function parsePublishModeWarning(warning: string | null | undefined): string[] {
  if (!warning?.trim()) return []
  return warning
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

export function publishModeWarningVariant(mode: string): 'info' | 'warning' | 'danger' {
  if (mode === 'http_direct' || mode === 'uvicorn_selfsigned') return 'danger'
  if (mode === 'nginx_selfsigned') return 'warning'
  return 'warning'
}

export function publishUvicornWarningsTitle(mode: string, warnings: string[]): string {
  if (warnings.some((line) => line.includes('Nginx') || line.includes('443'))) {
    return 'Uvicorn: какой адрес открывать'
  }
  if (mode === 'uvicorn_le' && warnings.some((line) => line.includes("Let's Encrypt"))) {
    return 'Uvicorn: сертификат на сервере'
  }
  return 'Uvicorn: перед применением'
}

export function publishModeWarningTitle(mode: string): string {
  if (mode === 'http_direct') return 'Небезопасный режим'
  if (mode === 'nginx_selfsigned') return 'Nginx — только для тестов'
  if (mode === 'uvicorn_selfsigned') return 'Uvicorn — только для тестов'
  return 'Внимание'
}

export function shouldShowAddressHint(mode: string): boolean {
  return (
    mode === 'nginx_le' ||
    mode === 'uvicorn_le' ||
    mode === 'nginx_custom' ||
    mode === 'uvicorn_custom' ||
    mode === 'nginx_selfsigned' ||
    mode === 'uvicorn_selfsigned'
  )
}

export function publishAddressHint(mode: string): { title: string; lines: string[] } {
  if (mode === 'nginx_le') {
    return {
      title: 'Адрес входа (Nginx)',
      lines: ["Let's Encrypt на домен — открывайте https://домен/ (TLS на Nginx)."],
    }
  }
  if (mode === 'uvicorn_le') {
    return {
      title: 'Адрес входа (uvicorn)',
      lines: ["Let's Encrypt на домен — открывайте https://домен:порт/ (TLS на uvicorn)."],
    }
  }
  if (mode === 'nginx_custom') {
    return {
      title: 'Адрес входа (Nginx)',
      lines: ['Открывайте https://домен/ — сертификат должен совпадать с адресом.'],
    }
  }
  if (mode === 'uvicorn_custom') {
    return {
      title: 'Адрес входа (uvicorn)',
      lines: ['Открывайте https://домен:порт/ — сертификат должен совпадать с адресом.'],
    }
  }
  if (mode === 'nginx_selfsigned') {
    return {
      title: 'Адрес входа (Nginx)',
      lines: ['https://домен/ или https://IP/ — HTTPS принимает Nginx (обычно порт 443).'],
    }
  }
  if (mode === 'uvicorn_selfsigned') {
    return {
      title: 'Адрес входа (uvicorn)',
      lines: ['https://домен:порт/ или https://IP:порт/ — порт из поля «Порт приложения».'],
    }
  }
  return { title: '', lines: [] }
}
