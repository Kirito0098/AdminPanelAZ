import { ExternalLink, FileText } from 'lucide-react'
import { Link } from 'react-router-dom'
import StatusPanel from '@/components/noc/StatusPanel'
import { Button } from '@/components/ui/button'

const routingFiles = [
  { key: 'include_ips', title: 'include-ips.txt', desc: 'Базовые IP для маршрутизации' },
  { key: 'exclude_ips', title: 'exclude-ips.txt', desc: 'Исключения из маршрутизации' },
  { key: 'forward_ips', title: 'forward-ips.txt', desc: 'IP для форвардинга' },
  { key: 'drop_ips', title: 'drop-ips.txt', desc: 'IP для блокировки' },
  { key: 'include_hosts', title: 'include-hosts.txt', desc: 'Домены для маршрутизации' },
  { key: 'exclude_hosts', title: 'exclude-hosts.txt', desc: 'Исключения доменов' },
]

interface FilesTabProps {
  isAdmin: boolean
}

export default function FilesTab({ isAdmin }: FilesTabProps) {
  return (
    <StatusPanel title="Файлы маршрутизации" icon={FileText}>
      <p className="mb-4 text-sm text-muted-foreground">
        Ручное редактирование базовых списков include/exclude. После сохранения файлов выполните
        «Применить (doall.sh)» для активации на узле.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        {routingFiles.map((f) => (
          <div
            key={f.key}
            className="flex items-center justify-between rounded-lg border p-4 transition-colors hover:bg-muted/40"
          >
            <div>
              <div className="font-medium text-sm">{f.title}</div>
              <div className="text-xs text-muted-foreground">{f.desc}</div>
            </div>
            {isAdmin && (
              <Button variant="ghost" size="sm" asChild>
                <Link to={`/edit-files?file=${f.key}`}>
                  <ExternalLink size={14} className="mr-1" />
                  Открыть
                </Link>
              </Button>
            )}
          </div>
        ))}
      </div>

      {isAdmin && (
        <div className="mt-6">
          <Button asChild>
            <Link to="/edit-files">
              <FileText size={14} className="mr-1.5" />
              Перейти в редактор файлов
            </Link>
          </Button>
        </div>
      )}

      {!isAdmin && (
        <p className="mt-4 text-sm text-muted-foreground">
          Редактирование файлов доступно только администраторам.
        </p>
      )}
    </StatusPanel>
  )
}
