import type { VpnNetworkPublishMode, VpnNetworkSettings } from '@/types'

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

function hasLetsEncryptSuggestion(settings: VpnNetworkSettings | null): boolean {
  return Boolean(settings?.ssl_cert_suggestions?.some((item) => item.source === 'letsencrypt'))
}

export function guessPublishAccessUrl(
  mode: string,
  domain: string,
  backendPort: string,
  httpsPublicPort: string,
  settings: VpnNetworkSettings | null,
): string | undefined {
  const host = domainHost(domain)
  if (!host) return undefined

  if (mode.startsWith('nginx_')) {
    const port = Number(httpsPublicPort)
    return port === 443 ? `https://${host}/` : `https://${host}:${port}/`
  }

  if (mode.startsWith('uvicorn_')) {
    const port = Number(backendPort)
    if (port !== 443 && hasLetsEncryptSuggestion(settings)) {
      return `https://${host}/`
    }
    return port === 443 ? `https://${host}/` : `https://${host}:${port}/`
  }

  if (mode === 'http_direct') {
    return `http://${host}:${backendPort}/`
  }

  return undefined
}

export function filterPublishWarningsForMode(mode: string, warnings: string[]): string[] {
  if (mode.startsWith('nginx_')) {
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
    return warnings
      .filter((line) => !line.includes('HSTS') && !line.includes('самоподпис'))
      .map((line) => {
        if (line.includes('уже есть Let')) {
          return 'Let\'s Encrypt уже есть — будет использован для входа через порт 443 (редирект на uvicorn).'
        }
        if (line.includes('выберите «HTTPS на uvicorn')) {
          return ''
        }
        return line
      })
      .filter(Boolean)
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
): PublishConfirmPlan {
  const host = domainHost(domain)
  const accessUrl = guessPublishAccessUrl(mode, domain, backendPort, httpsPublicPort, settings)
  const filteredWarnings = filterPublishWarningsForMode(mode, settings?.uvicorn_publish_warnings ?? [])

  if (mode === 'http_direct') {
    return {
      alertVariant: 'danger',
      alertTitle: 'Небезопасный режим',
      bullets: [
        modeInfo.warning ||
          'Панель будет доступна по HTTP без TLS — только для LAN или тестов.',
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
    if (mode === 'nginx_le' && hasLetsEncryptSuggestion(settings)) {
      bullets.unshift(`Сертификат Let's Encrypt для ${host || 'домена'} уже есть — будет переиспользован.`)
    }
    if (mode === 'nginx_custom' && hasLetsEncryptSuggestion(settings)) {
      bullets.unshift('Будут использованы указанные или найденные на сервере сертификаты.')
    }
    if (mode === 'nginx_selfsigned') {
      bullets.push('Браузер может предупредить о самоподписанном сертификате.')
    }
    if (settings?.nginx_installed === false) {
      bullets.push('Nginx будет установлен, если ещё не установлен.')
    }
    return {
      alertVariant: 'info',
      alertTitle: 'Что будет настроено',
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
    if (filteredWarnings.length > 0) {
      bullets.push(...filteredWarnings)
    } else if (mode === 'uvicorn_le') {
      bullets.push('Если сертификата ещё нет — certbot попробует выпустить его без остановки других сайтов.')
    }

    const isRiskySelfSigned =
      mode === 'uvicorn_selfsigned' &&
      filteredWarnings.some((line) => line.includes('HSTS'))

    return {
      alertVariant: isRiskySelfSigned ? 'danger' : filteredWarnings.length > 0 ? 'warning' : 'info',
      alertTitle: isRiskySelfSigned ? 'Ограничения режима' : 'Перед применением',
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
): string[] {
  return filterPublishWarningsForMode(mode, settings.uvicorn_publish_warnings ?? [])
}

export function hasLetsEncryptHint(settings: VpnNetworkSettings | null): boolean {
  return hasLetsEncryptSuggestion(settings)
}
