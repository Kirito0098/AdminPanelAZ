import type { CidrPipelineTask } from '@/types'
import type { IngestKind, PipelineStage } from '@/components/routing/utils'

/** Auto-refresh interval for routing data, seconds. */
export const REFRESH_INTERVAL = 60

export type RoutingLoadOptions = {
  initial?: boolean
  manual?: boolean
  fullMeta?: boolean
}

export type LoadRouting = (opts?: RoutingLoadOptions) => Promise<void>

export type PipelineMetaOptions = { light?: boolean }

/** Late-bound pipeline meta reload: the data hook owns it, the pipeline hook calls it. */
export type ReloadPipelineMeta = (opts?: PipelineMetaOptions) => Promise<void>

export type AttachPipelineTask = (
  taskId: string,
  stage: PipelineStage,
  okMsg: string,
  opts?: { force?: boolean; initialTask?: CidrPipelineTask; ingestKind?: IngestKind },
) => void
