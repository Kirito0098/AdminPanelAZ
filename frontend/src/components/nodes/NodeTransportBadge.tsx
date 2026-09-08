import { Badge } from '@/components/ui/badge'
import type { Node } from '@/types'

export default function NodeTransportBadge({ node }: { node: Node }) {
  if (node.is_local) {
    return <span className="text-muted-foreground">—</span>
  }
  return node.mtls_enabled ? (
    <Badge variant="default">mTLS</Badge>
  ) : (
    <Badge variant="outline">HTTP</Badge>
  )
}
