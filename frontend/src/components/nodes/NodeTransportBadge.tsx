import { Badge } from '@/components/ui/badge'
import type { Node } from '@/types'

function transportState(node: Node): { label: string; secure: boolean } {
  const raw = (node.transport || (node.mtls_enabled ? 'mtls' : 'http')).toLowerCase()
  if (raw === 'mtls') return { label: 'mTLS', secure: true }
  if (raw === 'ssh') return { label: 'SSH', secure: true }
  return { label: 'HTTP', secure: false }
}

export default function NodeTransportBadge({ node }: { node: Node }) {
  if (node.is_local) {
    return <span className="text-muted-foreground">—</span>
  }
  const { label, secure } = transportState(node)
  return secure ? (
    <Badge variant="default">{label}</Badge>
  ) : (
    <Badge variant="outline">{label}</Badge>
  )
}
