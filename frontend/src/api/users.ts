import { apiFetch, apiFetchResponse } from './http'
import type {
  TelegramLinkCodeResponse,
  UserProvisionedCreate,
  UserProvisionedResponse,
  UserProvisioningApply,
  UserProvisioningCard,
  UserProvisioningUpdate,
  UserStatsResponse,
} from '../types'

export interface UserProvisionSummary {
  id: number
  username: string
  role: string
  client_base_name: string | null
  plan_config_indexes: number[] | null
  desired_protocols: string[] | null
  panel_login_enabled: boolean
  provision_state: string
  access_until: string | null
  node_ids: number[]
  config_quota: number | null
}

/** POST /users/provisioned — создать абонента с планом и поставить задачу применения. */
export async function createProvisionedUser(data: UserProvisionedCreate) {
  return apiFetch<UserProvisionedResponse>('/users/provisioned', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** GET /users/{id}/provisioning — карточка абонента (план, задача, конфиги). */
export async function getProvisioning(userId: number) {
  return apiFetch<UserProvisioningCard>(`/users/${userId}/provisioning`)
}

/** PUT /users/{id}/provisioning — задать желаемое состояние (узлы, протоколы, имена, базовое имя). */
export async function updateProvisioning(userId: number, data: UserProvisioningUpdate) {
  return apiFetch<UserProvisionedResponse>(`/users/${userId}/provisioning`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

/** POST /users/{id}/provisioning/apply — применить/повторить план. */
export async function applyProvisioning(userId: number, data: UserProvisioningApply) {
  return apiFetch<{ task_id: string }>(`/users/${userId}/provisioning/apply`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** POST /users/{id}/provisioning/configs — добавить имя плана (следующий свободный индекс). */
export async function addProvisioningConfig(userId: number) {
  return apiFetch<{ index: number; task_id: string; user: UserProvisionSummary }>(
    `/users/${userId}/provisioning/configs`,
    { method: 'POST' },
  )
}

/** DELETE /users/{id}/provisioning/configs/{index} — убрать имя плана. confirm_deletions → query. */
export async function removeProvisioningConfig(
  userId: number,
  index: number,
  confirmDeletions = false,
) {
  const qs = confirmDeletions ? '?confirm_deletions=true' : ''
  return apiFetch<UserProvisionedResponse>(
    `/users/${userId}/provisioning/configs/${index}${qs}`,
    { method: 'DELETE' },
  )
}

/* ------------------------- D2 операции с конфигами абонента ------------------------- */

export interface UserConfigFile {
  protocol: string
  variant: string
  filename: string
  path: string
  download_filename?: string
}

export async function getUserConfigFiles(userId: number, configId: number) {
  return apiFetch<{ files: UserConfigFile[] }>(`/users/${userId}/configs/${configId}/files`)
}

export async function downloadUserConfigFile(userId: number, configId: number, path: string) {
  return apiFetchResponse(
    `/users/${userId}/configs/${configId}/download?path=${encodeURIComponent(path)}`,
  )
}

export async function qrUserConfigFile(userId: number, configId: number, path: string) {
  return apiFetchResponse(`/users/${userId}/configs/${configId}/qr?path=${encodeURIComponent(path)}`)
}

export interface ConfigAccessOp {
  op: 'block_temp' | 'block_perm' | 'unblock'
  days?: number
}

export async function setUserConfigAccessOp(userId: number, configId: number, op: ConfigAccessOp) {
  return apiFetch<{ message: string }>(`/users/${userId}/configs/${configId}/access`, {
    method: 'POST',
    body: JSON.stringify(op),
  })
}

export async function deleteUserConfig(userId: number, configId: number) {
  return apiFetch<{ message: string }>(`/users/${userId}/configs/${configId}`, {
    method: 'DELETE',
  })
}

/* ------------------------- статистика ------------------------- */

export async function getUserStats(userId: number, days = 30) {
  const qs = `?days=${Math.max(1, Math.min(365, days))}`
  return apiFetch<UserStatsResponse>(`/users/${userId}/stats${qs}`)
}

/* ------------------------- Telegram: код привязки ------------------------- */

export async function createUserTelegramLinkCode(userId: number) {
  return apiFetch<TelegramLinkCodeResponse>(`/users/${userId}/telegram-link-code`, {
    method: 'POST',
  })
}

/* ------------------------- удаление пользователя ------------------------- */

export async function deleteProvisionedUser(userId: number) {
  return apiFetch<{ message: string }>(`/users/${userId}`, { method: 'DELETE' })
}
