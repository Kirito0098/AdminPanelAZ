import { apiFetch } from './http'

export async function getEditFiles() {
  return apiFetch<import('../types').EditFileEntry[]>('/edit-files')
}

export async function getEditFileContent(key: string) {
  return apiFetch<{ key: string; content: string }>(`/edit-files/${key}`)
}

export async function saveEditFile(key: string, content: string) {
  return apiFetch(`/edit-files/${key}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

export async function saveEditFilesBatch(files: Record<string, string>, runDoall = false) {
  return apiFetch<{ message: string; detail?: string }>('/edit-files/batch', {
    method: 'POST',
    body: JSON.stringify({ files, run_doall: runDoall }),
  })
}

export interface EditFileTransferNodeResult {
  node_id: number
  node_name: string | null
  status: 'success' | 'failed' | 'skipped'
  transferred_files: string[]
  failed?: Array<{ file: string; error: string }>
  error?: string | null
  doall_output?: string | null
}

export interface EditFileTransferResult {
  success: boolean
  message: string
  source_node_id: number
  source_node_name: string
  files: string[]
  file_keys: string[]
  run_doall: boolean
  nodes_success: number
  nodes_failed: number
  nodes_skipped: number
  total_transferred: number
  per_node: EditFileTransferNodeResult[]
}

export async function transferEditFiles(payload: {
  file_keys: string[]
  target_node_ids?: number[] | null
  all_online?: boolean
  source_node_id?: number | null
  run_doall?: boolean
  content_overrides?: Record<string, string> | null
}) {
  return apiFetch<EditFileTransferResult>('/edit-files/transfer', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
