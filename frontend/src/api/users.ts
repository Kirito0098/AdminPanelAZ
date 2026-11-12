import { apiFetch, apiFetchResponse, parseQrResponse, type QrBlobResult } from './http'
import type {
  AccessRequestResponse,
  ApproveRequest,
  BulkNodesPreviewResponse,
  BulkNodesRequest,
  BulkUsersRequest,
  BulkUsersResult,
  PresetResponse,
  RejectRequest,
  TelegramLinkCodeResponse,
  User,
  UserFromExistingCreate,
  UserFromExistingResponse,
  UserHistoryEntry,
  UserProvisionedCreate,
  UserProvisionedResponse,
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

/** POST /users/from-existing — создать абонента из существующих конфигов. */
export async function createUserFromExisting(data: UserFromExistingCreate) {
  return apiFetch<UserFromExistingResponse>('/users/from-existing', {
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

export async function fetchUserConfigQrBlob(
  userId: number,
  configId: number,
  path: string,
): Promise<QrBlobResult> {
  const response = await apiFetchResponse(
    `/users/${userId}/configs/${configId}/qr?path=${encodeURIComponent(path)}`,
  )
  return parseQrResponse(response)
}

interface ConfigAccessOp {
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

/** GET /users/presets — список шаблонов (только если модуль включён). */
export async function listPresets() {
  return apiFetch<PresetResponse[]>('/users/presets')
}

/* ------------------------- заявки на доступ ------------------------- */

/** GET /users/requests — список заявок (с фильтрами ?status=&type=). */
export async function listRequests(params?: {
  status?: string
  type?: string
  q?: string
  limit?: number
  offset?: number
}) {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.type) qs.set('type', params.type)
  if (params?.q) qs.set('q', params.q)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  return apiFetch<AccessRequestResponse[]>(`/users/requests${qs.toString() ? `?${qs}` : ''}`)
}

/** GET /users/requests/count — сколько заявок с таким статусом. */
export async function getRequestsCount(status?: string): Promise<number> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  const data = await apiFetch<{ count: number }>(`/users/requests/count${qs}`)
  return data.count
}

/** GET /users/requests/{id}/receipt — превью чека оплаты (JPEG). */
export async function getRequestReceipt(requestId: number) {
  const response = await apiFetchResponse(`/users/requests/${requestId}/receipt`)
  return response.blob()
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

/* ------------------- Массовые операции над абонентами ------------------- */

/** POST /users/bulk — массовая операция (extend/suspend/resume/limit/delete). */
export async function bulkUsers(data: BulkUsersRequest) {
  return apiFetch<BulkUsersResult>('/users/bulk', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** GET /users/{id}/history — история действий по абоненту. */
export async function getUserHistory(userId: number, limit = 50) {
  return apiFetch<UserHistoryEntry[]>(`/users/${userId}/history?limit=${limit}`)
}

/* ------------------- Массовое уведомление в Telegram (D5) ------------------- */

interface BulkNotifyPayload {
  user_ids: number[]
  text: string
}

/** POST /users/bulk/notify — запустить фоновую рассылку. */
export async function startBulkNotify(payload: BulkNotifyPayload) {
  return apiFetch<{ task_id: string }>('/users/bulk/notify', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** GET /users/bulk/notify/tasks/{id}/report — JSON-отчёт по рассылке. */
export async function downloadBulkNotifyReport(taskId: string) {
  return apiFetchResponse(`/users/bulk/notify/tasks/${encodeURIComponent(taskId)}/report`)
}

export interface CooldownBlockedItem {
  telegram_id: string
  name: string
  request_type: string
  rejected_at: string
  until: string
}

export interface CooldownSettings {
  hours: number
  total: number
  blocked: CooldownBlockedItem[]
}

/** GET /users/requests/cooldown — настройка кулдауна и страница списка. */
export async function getRequestsCooldown(
  params: { limit?: number; offset?: number; q?: string } = {},
): Promise<CooldownSettings> {
  const search = new URLSearchParams()
  if (params.limit) search.set('limit', String(params.limit))
  if (params.offset) search.set('offset', String(params.offset))
  if (params.q) search.set('q', params.q)
  const qs = search.toString()
  return apiFetch<CooldownSettings>(qs ? `/users/requests/cooldown?${qs}` : '/users/requests/cooldown')
}

/** PUT /users/requests/cooldown — часы кулдауна после отказа (0 — выключен). */
export async function updateRequestsCooldown(hours: number): Promise<CooldownSettings> {
  return apiFetch<CooldownSettings>('/users/requests/cooldown', {
    method: 'PUT',
    body: JSON.stringify({ hours }),
  })
}

/** POST /users/requests/cooldown/release — снять кулдаун с Telegram ID. */
export async function releaseRequestsCooldown(telegramId: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>('/users/requests/cooldown/release', {
    method: 'POST',
    body: JSON.stringify({ telegram_id: telegramId }),
  })
}
