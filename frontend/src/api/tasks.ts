import { apiFetch, apiFetchAtBase } from './http'
import type { BackgroundTask } from '../types'

export async function getBackgroundTask(taskId: string) {
  return apiFetch<BackgroundTask>(`/tasks/${encodeURIComponent(taskId)}`)
}

export async function getBackgroundTaskForApiBase(taskId: string, apiBaseOverride: string) {
  return apiFetchAtBase<BackgroundTask>(
    apiBaseOverride,
    `/tasks/${encodeURIComponent(taskId)}`,
  )
}
