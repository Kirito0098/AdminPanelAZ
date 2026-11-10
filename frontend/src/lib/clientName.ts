/** Разрешённые имена VPN-клиентов: те же правила, что в backend/app/services/client_names.py. */
export const CLIENT_NAME_RE = /^[a-zA-Z0-9_-]{1,32}$/

export const CLIENT_NAME_HINT = 'Имя: латиница, цифры, _ и -, до 32 символов'

export function isValidClientName(name: string): boolean {
  return CLIENT_NAME_RE.test(name.trim())
}
