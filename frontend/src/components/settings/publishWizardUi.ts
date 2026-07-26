import { ApiError } from '@/api/client'
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

export function formatPublicHttpsHost(host: string, httpsPublicPort: string | number): string {
  const trimmed = host.trim().split(':')[0]
  if (!trimmed) return ''
  const port = Number(httpsPublicPort)
  if (!Number.isInteger(port) || port < 1 || port > 65535 || port === 443) {
    return trimmed
  }
  return `${trimmed}:${port}`
}

export function formatPublicHttpsOrigin(host: string, httpsPublicPort: string | number): string {
  const publicHost = formatPublicHttpsHost(host, httpsPublicPort)
  if (!publicHost) return 'https://ваш-домен'
  return `https://${publicHost}`
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

function publishPathSuffix(accessPath: string): string {
  const trimmed = accessPath.trim().replace(/\/+$/, '')
  if (!trimmed) return '/'
  const normalized = trimmed.startsWith('/') ? trimmed : `/${trimmed}`
  return `${normalized}/`
}

export function guessPublishAccessUrl(
  mode: string,
  domain: string,
  backendPort: string,
  httpsPublicPort: string,
  settings: VpnNetworkSettings | null,
  domainLetsEncrypt?: boolean | null,
  accessPath = '',
): string | undefined {
  const host = domainHost(domain)
  const pathSuffix = mode.startsWith('nginx_') ? publishPathSuffix(accessPath) : '/'

  if (mode.startsWith('nginx_')) {
    if (!host) return undefined
    const port = Number(httpsPublicPort)
    return port === 443 ? `https://${host}${pathSuffix}` : `https://${host}:${port}${pathSuffix}`
  }

  if (mode.startsWith('uvicorn_')) {
    if (!host) return undefined
    const port = Number(backendPort)
    return port === 443 ? `https://${host}${pathSuffix}` : `https://${host}:${port}${pathSuffix}`
  }

  if (mode === 'http_direct') {
    const accessHost = settings?.server_primary_ip?.trim()
    if (!accessHost) return undefined
    return `http://${accessHost}:${backendPort}${pathSuffix}`
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
  accessPath = '',
  nginxSubpathIntegrate = true,
): PublishConfirmPlan {
  const host = domainHost(domain)
  const accessUrl = guessPublishAccessUrl(
    mode,
    domain,
    backendPort,
    httpsPublicPort,
    settings,
    domainLetsEncrypt,
    accessPath,
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
    if (accessPath.trim()) {
      bullets.push(`Панель будет доступна по подпути ${publishPathSuffix(accessPath)} на домене.`)
      if (settings?.shared_domain_status_openvpn) {
        bullets.push(
          'На домене обнаружен StatusOpenVPN — панель встроится рядом с /status/ (только sites-enabled, с бэкапом).',
        )
        if (!nginxSubpathIntegrate) {
          bullets.push('Интеграция со StatusOpenVPN выключена — snippet будет создан, include нужно добавить вручную.')
        }
      } else if (!settings?.shared_domain_foreign_vhost) {
        bullets.push('Корень домена и другие пути вне подпути будут отдавать 404 — без редиректа, чтобы не раскрывать адрес панели.')
      } else {
        bullets.push('На домене уже есть другой сайт — панель встроится в его nginx vhost (snippet).')
        bullets.push('Корень домена остаётся за другим проектом — настройте редирект вручную, если нужно.')
      }
    }
    bullets.push(
      'После применения откройте адрес панели из уведомления. Если страница не загрузится сразу — подождите до 5 минут: сервис перезапускается.',
    )
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

export function publishAddressHint(
  mode: string,
  httpsPublicPort = '443',
): { title: string; lines: string[] } {
  const portHint =
    Number(httpsPublicPort) === 443
      ? 'https://домен/'
      : `https://домен:${httpsPublicPort}/`
  if (mode === 'nginx_le') {
    return {
      title: 'Адрес входа (Nginx)',
      lines: [`Let's Encrypt на домен — открывайте ${portHint} (TLS на Nginx).`],
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
      lines: [`Открывайте ${portHint} — сертификат должен совпадать с адресом.`],
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
      lines: [`${portHint} или https://IP/ — HTTPS принимает Nginx (порт из поля «Публичный порт HTTPS»).`],
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

export const PUBLISH_RESTART_WAIT_NOTICE =
  'Если страница не откроется сразу, подождите до 5 минут — сервис, скорее всего, перезапускается.'

export function buildPublishCompleteNotice(accessUrl?: string | null): string {
  const url = accessUrl?.trim()
  if (url) {
    return `Перейдите по адресу: ${url}. ${PUBLISH_RESTART_WAIT_NOTICE}`
  }
  return PUBLISH_RESTART_WAIT_NOTICE
}

export const PUBLISH_PATH_MOVED_TOAST = `Панель переезжает на новый адрес. ${PUBLISH_RESTART_WAIT_NOTICE}`

export function isLikelyPublishPathMovedPollError(
  message: string,
  expectedAccessUrl?: string | null,
): boolean {
  if (!expectedAccessUrl?.trim()) return false
  const text = message.toLowerCase()
  const pollError = text.includes('ошибка опроса') || text.includes('ошибка отслеживания')
  const htmlBody = text.includes('<!doctype') || text.includes('<html') || text.includes('404 not found')
  const notFound = text.includes('404') || text.includes('не найден')
  const restarting = text.includes('502') || text.includes('503') || text.includes('временно недоступен')
  return pollError && (htmlBody || notFound || restarting)
}

export function resolvePublishTaskErrorMessage(
  message: string,
  expectedAccessUrl?: string | null,
): string {
  if (isLikelyPublishPathMovedPollError(message, expectedAccessUrl)) {
    return PUBLISH_PATH_MOVED_TOAST
  }
  return message
}

export function isPublishPathMovedPollMessage(
  message: string,
  expectedAccessUrl?: string | null,
): boolean {
  if (message === PUBLISH_PATH_MOVED_TOAST) return !!expectedAccessUrl?.trim()
  if (message.includes(PUBLISH_RESTART_WAIT_NOTICE)) return !!expectedAccessUrl?.trim()
  return isLikelyPublishPathMovedPollError(message, expectedAccessUrl)
}

export function buildPublishPollBusyNotice(accessUrl?: string | null): string {
  const url = accessUrl?.trim()
  if (url) {
    return `Панель доступна по адресу: ${url}. ${PUBLISH_RESTART_WAIT_NOTICE}`
  }
  return PUBLISH_PATH_MOVED_TOAST
}

export const PUBLISH_START_LOST_CONNECTION_NOTICE =
  'Связь с сервером прервалась — это нормально при перезапуске. Публикация, скорее всего, уже запущена. Откройте новый адрес через несколько минут.'

export function isPublishStartTransientError(err: unknown): boolean {
  if (err instanceof ApiError) {
    if (err.status === 0 || [502, 503, 504].includes(err.status)) return true
  }
  if (err instanceof TypeError) return true
  if (err instanceof Error) {
    const text = err.message.toLowerCase()
    return (
      text.includes('failed to fetch') ||
      text.includes('networkerror') ||
      text.includes('network error') ||
      text.includes('load failed') ||
      text.includes('перезапуск')
    )
  }
  return false
}

export function formatPublishStartError(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error && err.message.trim()) return err.message
  return 'Ошибка запуска публикации'
}

export function publishConflictTaskId(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.status !== 409 || !err.payload || typeof err.payload !== 'object') {
    return null
  }
  const taskId = (err.payload as { active_task_id?: unknown }).active_task_id
  return typeof taskId === 'string' && taskId.trim() ? taskId.trim() : null
}

export function buildPublishStartedNotice(accessUrl?: string | null): string {
  const url = accessUrl?.trim()
  if (url) {
    return `Публикация запущена. Перейдите по адресу: ${url}. ${PUBLISH_RESTART_WAIT_NOTICE}`
  }
  return `Публикация запущена. ${PUBLISH_RESTART_WAIT_NOTICE}`
}

export function isPublishTransientRestartError(err: unknown, message: string): boolean {
  const status =
    err && typeof err === 'object' && 'status' in err ? Number((err as { status: unknown }).status) : NaN
  if ([404, 502, 503].includes(status)) return true
  const text = message.toLowerCase()
  return (
    text.includes('502') ||
    text.includes('503') ||
    text.includes('404') ||
    text.includes('временно недоступен') ||
    text.includes('переезжает') ||
    text.includes('перезапускается')
  )
}
