import { apiFetch, apiFetchResponse } from './http'
import type {
  AccessRequestResponse,
  ApproveRequest,
  BulkNodesPreviewResponse,
  BulkNodesRequest,
  PresetCreate,
  PresetResponse,
  PresetUpdate,
  RejectRequest,
  TelegramLinkCodeResponse,
  User,
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

export type UserQrContentMode = 'profile' | 'download-link'

export async function fetchUserConfigQrBlob(
  userId: number,
  configId: number,
  path: string,
): Promise<{ blob: Blob; contentMode: UserQrContentMode; downloadUrl?: string }> {
  const response = await qrUserConfigFile(userId, configId, path)
  const contentMode: UserQrContentMode =
    response.headers.get('X-Qr-Content') === 'download-link' ? 'download-link' : 'profile'
  const downloadUrl = response.headers.get('X-Qr-Download-Url') ?? undefined
  return { blob: await response.blob(), contentMode, downloadUrl }
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

/* ------------------------- Статус доступа (Stage 3) ------------------------- */

/** POST /users/{id}/suspend — приостановить доступ (sticky user_suspended). */
export async function suspendUser(
  userId: number,
  data: { reason?: string | null; show_reason?: boolean; notify_telegram?: boolean },
) {
  return apiFetch<User>(`/users/${userId}/suspend`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** POST /users/{id}/resume — снять приостановку (user_suspended). */
export async function resumeUser(
  userId: number,
  data: { notify_telegram?: boolean } = {},
) {
  return apiFetch<User>(`/users/${userId}/resume`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** POST /users/{id}/extend — продлить доступ на N дней (max(now, access_until) + days). */
export async function extendUserAccess(userId: number, days: number) {
  return apiFetch<User>(`/users/${userId}/extend`, {
    method: 'POST',
    body: JSON.stringify({ days }),
  })
}

/** POST /users/{id}/traffic-counter/reset — сбросить счётчик трафика абонента. */
export async function resetUserTrafficCounter(userId: number) {
  return apiFetch<User>(`/users/${userId}/traffic-counter/reset`, { method: 'POST' })
}

/** PATCH /users/{id} — лимит трафика абонента (null — снять ограничение). */
export async function setUserTrafficLimit(userId: number, trafficLimitBytes: number | null) {
  return apiFetch<User>(`/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify({ traffic_limit_bytes: trafficLimitBytes }),
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

/* ------------------------- пресеты предоставления доступа ------------------------- */

export interface PresetSummary {
  id: number
  name: string
  node_ids: number[]
  protocols: string[]
  config_count: number
  config_quota: number | null
  traffic_limit_bytes: number | null
  access_days: number | null
  is_default: boolean
  created_at: string
}

/** GET /users/presets — список шаблонов (только если модуль включён). */
export async function listPresets() {
  return apiFetch<PresetResponse[]>('/users/presets')
}

/** POST /users/presets — создать шаблон. */
export async function createPreset(data: PresetCreate) {
  return apiFetch<PresetResponse>('/users/presets', { method: 'POST', body: JSON.stringify(data) })
}

/** PUT /users/presets/{id} — обновить шаблон. */
export async function updatePreset(presetId: number, data: PresetUpdate) {
  return apiFetch<PresetResponse>(`/users/presets/${presetId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

/** DELETE /users/presets/{id} — удалить шаблон. */
export async function deletePreset(presetId: number) {
  return apiFetch<{ message: string }>(`/users/presets/${presetId}`, { method: 'DELETE' })
}

/* ------------------------- заявки на доступ ------------------------- */

/** GET /users/requests — список заявок (с фильтрами ?status=&type=). */
export async function listRequests(params?: { status?: string; type?: string }) {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.type) qs.set('type', params.type)
  return apiFetch<AccessRequestResponse[]>(`/users/requests${qs.toString() ? `?${qs}` : ''}`)
}

/** POST /users/requests/{id}/approve — одобрить заявку. */
export async function approveRequest(requestId: number, data: ApproveRequest) {
  return apiFetch<AccessRequestResponse>(`/users/requests/${requestId}/approve`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** POST /users/requests/{id}/reject — отклонить заявку. */
export async function rejectRequest(requestId: number, data: RejectRequest) {
  return apiFetch<AccessRequestResponse>(`/users/requests/${requestId}/reject`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/* ------------------- Массовые операции с серверами (Stage 4) ------------------- */

/** POST /users/bulk/nodes/preview — что изменится у пользователей и кто будет пропущен. */
export async function previewBulkNodes(body: BulkNodesRequest) {
  return apiFetch<BulkNodesPreviewResponse>('/users/bulk/nodes/preview', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** POST /users/bulk/nodes — запустить фоновую задачу (202 → {task_id}). */
export async function startBulkNodes(body: BulkNodesRequest) {
  return apiFetch<{ task_id: string }>('/users/bulk/nodes', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** GET /users/bulk/nodes/tasks/{task_id}/report — JSON-отчёт по завершённой задаче. */
export async function downloadBulkNodesReport(taskId: string) {
  return apiFetchResponse(`/users/bulk/nodes/tasks/${encodeURIComponent(taskId)}/report`)
}
