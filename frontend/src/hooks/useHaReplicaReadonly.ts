import { useNode } from '@/context/NodeContext'

/** True when the active node is an HA replica — client create/delete/block must use primary. */
export function useHaReplicaReadonly(): boolean {
  const { activeNodeHa } = useNode()
  return activeNodeHa?.role === 'replica'
}
