import BackgroundTaskProgress from '@/components/ui/BackgroundTaskProgress'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { CidrDeployPerNodeResult, CidrPipelineTask } from '@/types'

interface PipelineTaskProgressProps {
  task: CidrPipelineTask | null
}

function nodeStatusVariant(status: CidrDeployPerNodeResult['status']): 'default' | 'destructive' | 'secondary' {
  switch (status) {
    case 'success':
      return 'default'
    case 'failed':
      return 'destructive'
    default:
      return 'secondary'
  }
}

function nodeStatusLabel(status: CidrDeployPerNodeResult['status']): string {
  switch (status) {
    case 'success':
      return 'Успех'
    case 'failed':
      return 'Ошибка'
    case 'skipped':
      return 'Пропущен'
    default:
      return status
  }
}

function DeployPerNodeResults({ perNode }: { perNode: CidrDeployPerNodeResult[] }) {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="text-sm font-medium">Результат развёртывания по нодам</div>
      <div className="rounded-md border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Нода</TableHead>
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
                  <Badge variant={nodeStatusVariant(entry.status)}>{nodeStatusLabel(entry.status)}</Badge>
                </TableCell>
                <TableCell className="text-right font-mono text-sm">
                  {entry.pushed_files?.length ?? 0}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {entry.error ??
                    (entry.failed?.length
                      ? entry.failed.map((f) => `${f.file}: ${f.error}`).join('; ')
                      : '—')}
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
