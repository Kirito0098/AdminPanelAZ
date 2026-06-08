const WEB_SESSION_ID_KEY = 'web_session_id'

export function storeWebSessionId(id: string) {
  sessionStorage.setItem(WEB_SESSION_ID_KEY, id)
}

export function getWebSessionId(): string | null {
  return sessionStorage.getItem(WEB_SESSION_ID_KEY)
}

export function clearWebSessionId() {
  sessionStorage.removeItem(WEB_SESSION_ID_KEY)
}
