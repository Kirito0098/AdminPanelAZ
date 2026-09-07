import { apiFetch, apiFetchAtBase } from './http'

export async function getBackgroundTask(taskId: string) {
  return apiFetch<import('../types').BackgroundTask>(`/tasks/${encodeURIComponent(taskId)}`)
}

export async function getBackgroundTaskForApiBase(taskId: string, apiBaseOverride: string) {
  return apiFetchAtBase<import('../types').BackgroundTask>(
    apiBaseOverride,
    `/tasks/${encodeURIComponent(taskId)}`,
  )
}
