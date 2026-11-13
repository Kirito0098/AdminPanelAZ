import { useCallback, useEffect, useState } from 'react'
import type { MutableRefObject } from 'react'
import type { CidrDeployPreview } from '@/types'

interface Args {
  activeNodeId: number | undefined
  /** A changed provider selection invalidates a preview built for the old one. */
  selectedProviderFiles: string[] | null
  /** Set by requestRollback, read when the rollback task completes. */
  pendingRollbackStampRef: MutableRefObject<string | null>
  /** Latest stamp reported by a completed rollback task. */
  recentRollbackStamp: string | null
}

/** Deploy targets, deploy preview and rollback-backup selection. */
export function useDeployTargets({
  activeNodeId,
  selectedProviderFiles,
  pendingRollbackStampRef,
  recentRollbackStamp,
}: Args) {
  const [deployAllOnline, setDeployAllOnline] = useState(false)
  const [deployTargetNodeIds, setDeployTargetNodeIds] = useState<number[]>([])
  const [deployPreview, setDeployPreview] = useState<CidrDeployPreview | null>(null)
  const [deployPreviewLoading, setDeployPreviewLoading] = useState(false)
  const [rollbackStamp, setRollbackStamp] = useState<string | null>(null)

  useEffect(() => {
    if (activeNodeId && deployTargetNodeIds.length === 0) {
      setDeployTargetNodeIds([activeNodeId])
    }
  }, [activeNodeId, deployTargetNodeIds.length])

  // A deploy preview describes exactly the targets it was built for: a changed selection
  // must fetch a new one instead of confirming someone else's diff.
  useEffect(() => {
    setDeployPreview(null)
  }, [deployAllOnline, deployTargetNodeIds, selectedProviderFiles])

  const requestRollbackSelection = useCallback(
    (stamp: string) => {
      pendingRollbackStampRef.current = stamp
      setRollbackStamp(stamp)
    },
    [pendingRollbackStampRef],
  )

  return {
    deployAllOnline,
    setDeployAllOnline,
    deployTargetNodeIds,
    setDeployTargetNodeIds,
    deployPreview,
    setDeployPreview,
    deployPreviewLoading,
    setDeployPreviewLoading,
    rollbackStamp,
    setRollbackStamp,
    recentRollbackStamp,
    requestRollbackSelection,
  }
}
