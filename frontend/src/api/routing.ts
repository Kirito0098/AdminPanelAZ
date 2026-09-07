import { ApiError, apiFetch } from './http'

export async function getRoutingOverview() {
  return apiFetch<import('../types').RoutingOverview>('/routing/overview')
}

export async function toggleRoutingProvider(filename: string, enabled: boolean) {
  return apiFetch(`/routing/providers/${encodeURIComponent(filename)}/enabled`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  })
}

export async function getRoutingProviderContent(filename: string) {
  return apiFetch<import('../types').RoutingProviderContent>(
    `/routing/providers/${encodeURIComponent(filename)}`,
  )
}

export async function saveRoutingProviderContent(filename: string, content: string) {
  return apiFetch<{ filename: string; cidr_count: number }>(
    `/routing/providers/${encodeURIComponent(filename)}`,
    { method: 'PUT', body: JSON.stringify({ content }) },
  )
}

export async function getRoutingResults() {
  return apiFetch<{ files: import('../types').RouteResultFileEntry[] }>('/routing/results')
}

export async function getRoutingResultContent(key: string) {
  return apiFetch<{ key: string; filename: string; content: string; line_count: number }>(
    `/routing/results/${encodeURIComponent(key)}`,
  )
}

export async function syncRoutingProviders() {
  return apiFetch('/routing/sync', { method: 'POST' })
}

export async function applyRouting() {
  return apiFetch<import('../types').BackgroundTaskAcceptedResponse>('/routing/apply', { method: 'POST' })
}

export async function clearCidrDb(selectedFiles?: string[] | null) {
  return apiFetch<{ success: boolean; message: string }>('/routing/cidr-db/clear', {
    method: 'POST',
    body: JSON.stringify({ selected_files: selectedFiles ?? null }),
  })
}

export async function getCidrDbStatus() {
  return apiFetch<import('../types').CidrDbStatus>('/routing/cidr-db/status')
}

export async function getCidrDbSchedule() {
  return apiFetch<import('../types').CidrDbSchedule>('/routing/cidr-db/schedule')
}

export async function updateCidrDbSchedule(payload: import('../types').CidrDbScheduleUpdate) {
  return apiFetch<import('../types').CidrDbSchedule>('/routing/cidr-db/schedule', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function getCidrDbStatusSummary() {
  return apiFetch<{
    success: boolean
    total_cidrs: number
    active_task?: import('../types').CidrPipelineTask | null
  }>('/routing/cidr-db/status/summary')
}

export async function getAntifilterStatus() {
  return apiFetch<import('../types').AntifilterStatus>('/routing/cidr-db/antifilter/status')
}

export async function refreshCidrDb(options?: {
  selectedFiles?: string[] | null
  retryFailedMode?: 'last' | 'selected'
  dryRun?: boolean
}) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/refresh', {
    method: 'POST',
    body: JSON.stringify({
      selected_files: options?.selectedFiles ?? null,
      retry_failed_mode: options?.retryFailedMode ?? null,
      dry_run: options?.dryRun ?? false,
    }),
  })
}

export async function refreshAntifilter() {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/antifilter/refresh', {
    method: 'POST',
  })
}

export async function generateCidrFromDb(options?: {
  regions?: string[] | null
  filter_by_antifilter?: boolean
  exclude_ru_cidrs?: boolean
  apply_after?: boolean
  deploy_after?: boolean
  target_node_id?: number | null
  sync_after?: boolean
}) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/generate', {
    method: 'POST',
    body: JSON.stringify({
      action: 'generate',
      regions: options?.regions ?? null,
      filter_by_antifilter: options?.filter_by_antifilter ?? false,
      exclude_ru_cidrs: options?.exclude_ru_cidrs ?? false,
      apply_after: options?.apply_after ?? false,
      deploy_after: options?.deploy_after ?? false,
      target_node_id: options?.target_node_id ?? null,
      sync_after: options?.sync_after ?? false,
    }),
  })
}

export async function deployCidrToNode(options?: {
  target_node_id?: number | null
  target_node_ids?: number[] | null
  all_online?: boolean
  sync_after?: boolean
  apply_after?: boolean
  recreate_profiles_after?: boolean
  selected_files?: string[] | null
}) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/deploy', {
    method: 'POST',
    body: JSON.stringify({
      target_node_id: options?.target_node_id ?? null,
      target_node_ids: options?.target_node_ids ?? null,
      all_online: options?.all_online ?? false,
      sync_after: options?.sync_after ?? true,
      apply_after: options?.apply_after ?? false,
      recreate_profiles_after: options?.recreate_profiles_after ?? false,
      selected_files: options?.selected_files ?? null,
    }),
  })
}

export async function previewCidrDeploy(options?: {
  target_node_id?: number | null
  target_node_ids?: number[] | null
  all_online?: boolean
  selected_files?: string[] | null
}) {
  return apiFetch<import('../types').CidrDeployPreview>('/routing/cidr-db/deploy/preview', {
    method: 'POST',
    body: JSON.stringify({
      target_node_id: options?.target_node_id ?? null,
      target_node_ids: options?.target_node_ids ?? null,
      all_online: options?.all_online ?? false,
      selected_files: options?.selected_files ?? null,
    }),
  })
}

export async function rollbackCidrFromBackup(options: {
  backup_stamp: string
  selected_files?: string[] | null
  redeploy_after?: boolean
  target_node_id?: number | null
  target_node_ids?: number[] | null
  all_online?: boolean
  sync_after?: boolean
  apply_after?: boolean
}) {
  return apiFetch<{ success: boolean; task_id: string; message: string }>('/routing/cidr-db/rollback', {
    method: 'POST',
    body: JSON.stringify({
      backup_stamp: options.backup_stamp,
      selected_files: options.selected_files ?? null,
      redeploy_after: options.redeploy_after ?? true,
      target_node_id: options.target_node_id ?? null,
      target_node_ids: options.target_node_ids ?? null,
      all_online: options.all_online ?? false,
      sync_after: options.sync_after ?? true,
      apply_after: options.apply_after ?? false,
    }),
  })
}

export async function addCustomCidrProviderEntries(
  providerKey: string,
  payload: { cidrs?: string[]; cidrs_text?: string; asns?: string[] },
) {
  return apiFetch<{
    success: boolean
    message: string
    provider_key: string
    cidrs_added: number
    asns_added: number
    total_cidrs?: number
    active_asn_count?: number
  }>(`/routing/cidr-db/providers/${encodeURIComponent(providerKey)}/custom`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getCidrBackgroundTask(taskId: string) {
  const resp = await apiFetch<
    { success?: boolean; task?: import('../types').BackgroundTask } & import('../types').BackgroundTask
  >(`/routing/cidr-db/tasks/${encodeURIComponent(taskId)}`)
  if (resp?.task?.task_id) return resp.task
  if (resp?.task_id) return resp as import('../types').BackgroundTask
  throw new ApiError('Некорректный ответ сервера о статусе задачи', 500)
}
