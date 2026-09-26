import { runLatest, type LatestRequest } from './latestRequest'

/** The file and node whose content is in the editor. */
export interface LoadedEditFile {
  key: string
  nodeId: number | null
}

/**
 * Saving writes the editor text under the open file on the shown node: it must be the text read
 * from that file, otherwise one list overwrites another.
 */
export function editorMatchesTarget(
  loaded: LoadedEditFile | null,
  activeKey: string | null,
  activeNodeId: number | null,
): boolean {
  return loaded != null && activeKey != null && loaded.key === activeKey && loaded.nodeId === activeNodeId
}

/** Reads a file and applies it only if it is still the file opened last on the shown node. */
export function loadEditFile(
  requests: LatestRequest<number | null>,
  key: string,
  nodeId: number | null,
  read: (key: string) => Promise<{ content: string }>,
  handlers: {
    apply: (loaded: LoadedEditFile, content: string) => void
    fail: (err: unknown) => void
    settle?: () => void
  },
): Promise<void> {
  return runLatest(requests, () => read(key), {
    apply: (result) => handlers.apply({ key, nodeId }, result.content),
    fail: handlers.fail,
    settle: handlers.settle,
  })
}
