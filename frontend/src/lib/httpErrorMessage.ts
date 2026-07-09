const HTML_TITLE_RE = /<title>\s*([^<]+?)\s*<\/title>/i
const HTML_H1_RE = /<h1>\s*([^<]+?)\s*<\/h1>/i

const STATUS_MESSAGES: Record<number, string> = {
  400: 'Некорректный запрос (400).',
  401: 'Требуется авторизация (401).',
  403: 'Доступ запрещён (403).',
  404: 'Запрос не найден (404). Проверьте адрес панели или путь доступа.',
  408: 'Превышено время ожидания запроса (408).',
  429: 'Слишком много запросов (429). Подождите несколько секунд.',
  500: 'Внутренняя ошибка сервера (500).',
  502: 'Сервер временно недоступен (502). Возможен перезапуск панели — подождите и обновите страницу.',
  503: 'Сервис временно недоступен (503). Подождите и обновите страницу.',
  504: 'Превышено время ожидания ответа сервера (504).',
}

function looksLikeHtmlBody(body: string): boolean {
  const text = body.trim().toLowerCase()
  return (
    text.startsWith('<!doctype') ||
    text.startsWith('<html') ||
    (text.includes('<html') && text.includes('</html>')) ||
    (text.includes('<head>') && text.includes('<body>'))
  )
}

function extractHtmlTitle(body: string): string | null {
  const match = HTML_TITLE_RE.exec(body) || HTML_H1_RE.exec(body)
  return match?.[1]?.trim() || null
}

function defaultStatusMessage(status: number, fallback: string): string {
  return STATUS_MESSAGES[status] || `${fallback} (код ${status})`
}

export function normalizeHttpErrorDetail(
  detail: string,
  status: number,
  fallback = 'Ошибка запроса',
): string {
  const trimmed = detail.trim()
  if (!trimmed) return defaultStatusMessage(status, fallback)

  if (looksLikeHtmlBody(trimmed)) {
    const title = extractHtmlTitle(trimmed)
    if (title && STATUS_MESSAGES[status]) return STATUS_MESSAGES[status]
    if (title) return `Ошибка сервера: ${title}`
    return defaultStatusMessage(status, fallback)
  }

  if (trimmed.length > 400) {
    return `${trimmed.slice(0, 397)}…`
  }

  return trimmed
}

export function parseHttpErrorBody(
  body: string | null | undefined,
  status: number,
  fallback = 'Ошибка запроса',
): string {
  if (!body?.trim()) return defaultStatusMessage(status, fallback)

  try {
    const data = JSON.parse(body) as { detail?: unknown; message?: unknown }
    if (data.detail != null) {
      const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
      return normalizeHttpErrorDetail(detail, status, fallback)
    }
    if (typeof data.message === 'string') {
      return normalizeHttpErrorDetail(data.message, status, fallback)
    }
  } catch {
    // not JSON — treat as plain text or HTML
  }

  return normalizeHttpErrorDetail(body, status, fallback)
}
