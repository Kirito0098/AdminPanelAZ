import { AlertTriangle, CheckCircle2, Minus, Plus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { CidrDeployPreview } from '@/types'

interface DeployPreviewPanelProps {
  preview: CidrDeployPreview | null
  loading?: boolean
}

export default function DeployPreviewPanel({ preview, loading }: DeployPreviewPanelProps) {
  if (loading) {
    return (
      <div className="mb-4 rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        Загрузка предпросмотра…
      </div>
    )
  }
  if (!preview) return null

  const nodes = preview.per_node?.filter((n) => n.status === 'ok') ?? []

  return (
    <div className="mb-4 space-y-3 rounded-md border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Предпросмотр развёртывания</span>
        {preview.has_changes ? (
          <Badge variant="secondary" className="gap-1">
            <AlertTriangle size={12} />
            Есть изменения
          </Badge>
        ) : (
          <Badge variant="outline" className="gap-1">
            <CheckCircle2 size={12} />
            Без изменений
          </Badge>
        )}
      </div>
      <p className="text-sm text-muted-foreground">{preview.message}</p>

      {nodes.map((node) => (
        <div key={node.node_id} className="rounded-md border overflow-hidden">
          <div className="bg-muted/40 px-3 py-2 text-sm font-medium">
            {node.node_name ?? `Узел #${node.node_id}`}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              контроллер: {node.total_controller_routes ?? 0} маршр. · узел: {node.total_node_routes ?? 0} маршр.
              {(node.total_added ?? 0) > 0 || (node.total_removed ?? 0) > 0 ? (
                <>
                  {' '}
                  · <Plus size={10} className="inline" /> {node.total_added ?? 0}{' '}
                  <Minus size={10} className="inline" /> {node.total_removed ?? 0}
                </>
              ) : null}
            </span>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Файл</TableHead>
                <TableHead className="text-right">Контроллер</TableHead>
                <TableHead className="text-right">Узел</TableHead>
                <TableHead className="text-right">+ / −</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(node.files ?? []).map((file) => (
                <TableRow key={`${node.node_id}-${file.file}`}>
                  <TableCell className="font-mono text-xs">{file.file}</TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {file.controller_cidr_count ?? '—'}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">{file.node_cidr_count ?? '—'}</TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {file.diff?.changed ? (
                      <span className="text-amber-700 dark:text-amber-300">
                        +{file.diff.added} / −{file.diff.removed}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">0</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ))}
    </div>
  )
}
