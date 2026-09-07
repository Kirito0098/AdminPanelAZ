import { clearWebSessionId } from '@/lib/webSession'
import { apiFetch } from './http'

export type LoginResult =
  | { access_token: string; web_session_id?: string; requires_2fa?: false }
  | { requires_2fa: true; temp_token: string; passkey_available?: boolean }

export async function login(username: string, password: string): Promise<LoginResult> {
  return apiFetch<LoginResult>('/auth/login/json', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function loginWithCaptcha(
  username: string,
  password: string,
  captchaId: string,
  captchaText: string,
): Promise<LoginResult> {
  return apiFetch<LoginResult>('/auth/login/json', {
    method: 'POST',
    body: JSON.stringify({ username, password, captcha_id: captchaId, captcha_text: captchaText }),
  })
}

export async function login2FA(tempToken: string, code: string) {
  return apiFetch<{ access_token: string; web_session_id?: string }>('/auth/login/2fa', {
    method: 'POST',
    body: JSON.stringify({ temp_token: tempToken, code }),
  })
}

export async function logoutApi() {
  try {
    return await apiFetch('/auth/logout', { method: 'POST' })
  } finally {
    clearWebSessionId()
  }
}

export async function get2FAStatus() {
  return apiFetch<{ enabled: boolean; backup_codes_remaining: number }>('/auth/2fa/status')
}

export async function setup2FA() {
  return apiFetch<{ secret: string; otpauth_uri: string; qr_data_url: string }>('/auth/2fa/setup', {
    method: 'POST',
  })
}

export async function enable2FA(code: string) {
  return apiFetch<{ backup_codes: string[] }>('/auth/2fa/enable', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

export async function disable2FA(code: string) {
  return apiFetch('/auth/2fa/disable', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

export async function regenerate2FABackupCodes(code: string) {
  return apiFetch<{ backup_codes: string[] }>('/auth/2fa/regenerate-backup-codes', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

export type PasskeyCredential = {
  id: number
  nickname: string
  created_at: string
  last_used_at: string | null
}

export async function getPasskeys() {
  return apiFetch<{ credentials: PasskeyCredential[]; count: number }>('/auth/passkeys')
}

export async function getPasskeyRegisterOptions() {
  return apiFetch<{ options: Record<string, unknown> & { sessionKey?: string } }>(
    '/auth/passkeys/register/options',
    { method: 'POST' },
  )
}

export async function verifyPasskeyRegister(
  sessionKey: string,
  credential: unknown,
  nickname?: string,
) {
  return apiFetch<PasskeyCredential>('/auth/passkeys/register/verify', {
    method: 'POST',
    body: JSON.stringify({ session_key: sessionKey, credential, nickname }),
  })
}

export async function deletePasskey(credentialId: number) {
  return apiFetch('/auth/passkeys/' + credentialId, { method: 'DELETE' })
}

export async function renamePasskey(credentialId: number, nickname: string) {
  return apiFetch<PasskeyCredential>('/auth/passkeys/' + credentialId, {
    method: 'PATCH',
    body: JSON.stringify({ nickname }),
  })
}

export async function getPasskeyLoginOptions(tempToken: string) {
  return apiFetch<{ options: Record<string, unknown> & { sessionKey?: string } }>(
    '/auth/login/passkey/options',
    {
      method: 'POST',
      body: JSON.stringify({ temp_token: tempToken }),
    },
  )
}

export async function verifyPasskeyLogin(tempToken: string, sessionKey: string, credential: unknown) {
  return apiFetch<{ access_token: string; web_session_id?: string }>('/auth/login/passkey/verify', {
    method: 'POST',
    body: JSON.stringify({ temp_token: tempToken, session_key: sessionKey, credential }),
  })
}

export async function getCaptchaRequired() {
  return apiFetch<{ required: boolean }>('/auth/captcha/required')
}

export async function getTelegramLoginConfig() {
  return apiFetch<{
    enabled: boolean
    auth_method?: 'oidc' | 'legacy' | 'none'
    bot_username: string
    max_age_seconds?: number
    oidc_enabled?: boolean
    oidc_client_id?: string
    legacy_enabled?: boolean
    oidc_start_url?: string
  }>('/auth/telegram/config')
}

export async function getMe() {
  return apiFetch<import('../types').User>('/auth/me')
}

export async function changePassword(current: string, newPassword: string) {
  return apiFetch('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: current, new_password: newPassword }),
  })
}

export async function getActiveWebSessions() {
  return apiFetch<import('../types').ActiveWebSession[]>('/security/active-sessions')
}

export async function revokeActiveWebSession(sessionId: string) {
  return apiFetch(`/security/active-sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
}
