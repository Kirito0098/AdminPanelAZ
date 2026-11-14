import BackgroundTaskProgress from '@/components/ui/BackgroundTaskProgress'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { CidrDeployPerNodeResult, CidrPipelineTask } from '@/types'
import { statusBadgeVariant, statusLabel } from './utils'

interface PipelineTaskProgressProps {
  task: CidrPipelineTask | null
}

function deployDetails(entry: CidrDeployPerNodeResult): string {
  const updated = entry.updated_files?.length ?? 0
  if (entry.noop || updated === 0) {
    const deployed = (entry.synced_files?.length ?? entry.pushed_files?.length ?? 0) > 0
    return deployed ? 'без изменений' : '—'
  }
  return `изменено: ${updated}`
}

function DeployPerNodeResults({ perNode }: { perNode: CidrDeployPerNodeResult[] }) {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="text-sm font-medium">Результат развёртывания по узлам</div>
      <div className="rounded-md border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Узел</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead className="text-right">Файлов</TableHead>
              <TableHead>Детали</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {perNode.map((entry) => (
              <TableRow key={entry.node_id}>
                <TableCell className="text-sm">
                  {entry.node_name ?? `Узел #${entry.node_id}`}
                </TableCell>
                <TableCell>
                  <Badge variant={statusBadgeVariant(entry.status)}>{statusLabel(entry.status)}</Badge>
                </TableCell>
                <TableCell className="text-right font-mono text-sm">
                  {entry.synced_files?.length ?? entry.pushed_files?.length ?? 0}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {entry.error ??
                    (entry.failed?.length
                      ? entry.failed.map((f) => `${f.file}: ${f.error}`).join('; ')
                      : deployDetails(entry))}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

export default function PipelineTaskProgress({ task }: PipelineTaskProgressProps) {
  const perNode = task?.result?.per_node
  const showPerNode = perNode && perNode.length > 0 && task && ['completed', 'failed'].includes(task.status)

  return (
    <div className="space-y-4">
      <BackgroundTaskProgress task={task} />
      {showPerNode && <DeployPerNodeResults perNode={perNode} />}
    </div>
  )
}
