import { Badge } from '@/components/ui/badge'
import type { Node } from '@/types'

function transportLabel(node: Node): string {
  const raw = (node.transport || (node.mtls_enabled ? 'mtls' : 'http')).toLowerCase()
  if (raw === 'mtls') return 'mTLS'
  if (raw === 'ssh') return 'SSH'
  return 'HTTP'
}

export default function NodeTransportBadge({ node }: { node: Node }) {
  if (node.is_local) {
    return <span className="text-muted-foreground">—</span>
  }
  const label = transportLabel(node)
  const isSecure = label === 'mTLS' || label === 'SSH'
  return isSecure ? (
    <Badge variant="default">{label}</Badge>
  ) : (
    <Badge variant="outline">{label}</Badge>
  )
}
