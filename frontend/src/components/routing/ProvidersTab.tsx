import { useMemo, useState } from 'react'
import { Route, Search } from 'lucide-react'
import StatusPanel from '@/components/noc/StatusPanel'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { CidrDbStatus, CidrProviderInfo } from '@/types'
import { formatDt, statusBadgeVariant, statusLabel } from './utils'

interface ProvidersTabProps {
  providers: CidrProviderInfo[]
  cidrDb: CidrDbStatus | null
  isAdmin: boolean
  actionLoading: boolean
  onToggle: (filename: string, enabled: boolean, name: string) => void
}

export default function ProvidersTab({
  providers,
  cidrDb,
  isAdmin,
  actionLoading,
  onToggle,
}: ProvidersTabProps) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')

  const categories = useMemo(
    () => [...new Set(providers.map((p) => p.category))].sort(),
    [providers],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return providers.filter((p) => {
      const dbMeta = cidrDb?.providers?.[p.filename]
      const dbStatus = dbMeta?.refresh_status ?? 'never'
      if (statusFilter !== 'all' && dbStatus !== statusFilter) return false
      if (categoryFilter !== 'all' && p.category !== categoryFilter) return false
      if (!q) return true
      return (
        p.name.toLowerCase().includes(q) ||
        p.filename.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q)
      )
    })
  }, [providers, cidrDb, search, statusFilter, categoryFilter])

  if (providers.length === 0) {
    return (
      <EmptyState
        icon={Search}
        title="Нет провайдеров"
        description="Список CIDR-провайдеров пуст. Проверьте конфигурацию AntiZapret."
      />
    )
  }

  return (
    <StatusPanel title="CIDR-провайдеры" icon={Route}>
      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Поиск по имени, файлу..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Статус БД" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все статусы</SelectItem>
              <SelectItem value="ok">OK</SelectItem>
              <SelectItem value="partial">Частично</SelectItem>
              <SelectItem value="error">Ошибка</SelectItem>
              <SelectItem value="never">Нет данных</SelectItem>
            </SelectContent>
          </Select>
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Категория" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все категории</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-xs text-muted-foreground">Показано: {filtered.length}</span>
        </div>

        <div className="rounded-md border overflow-hidden">
          <div className="max-h-[min(70vh,600px)] overflow-auto">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-muted/95 backdrop-blur supports-[backdrop-filter]:bg-muted/80">
                <TableRow>
                  <TableHead>Провайдер</TableHead>
                  <TableHead>Категория</TableHead>
                  <TableHead className="text-right">CIDR (файл)</TableHead>
                  <TableHead className="text-right">CIDR (БД)</TableHead>
                  <TableHead>БД refresh</TableHead>
                  <TableHead>Статус</TableHead>
                  {isAdmin && <TableHead className="text-right">Действие</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((p, idx) => {
                  const dbMeta = cidrDb?.providers?.[p.filename]
                  return (
                    <TableRow
                      key={p.filename}
                      className={cn(idx % 2 === 1 && 'bg-muted/30')}
                    >
                      <TableCell>
                        <div className="font-medium">{p.name}</div>
                        <div className="text-xs text-muted-foreground font-mono">{p.filename}</div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{p.category}</Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{p.cidr_count}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {dbMeta?.cidr_count ?? '—'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusBadgeVariant(dbMeta?.refresh_status)}>
                          {statusLabel(dbMeta?.refresh_status)}
                        </Badge>
                        <div className="text-xs text-muted-foreground mt-1">
                          {formatDt(dbMeta?.last_refreshed_at)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={p.enabled ? 'default' : 'secondary'}>
                          {p.enabled ? 'Включён' : 'Выключен'}
                        </Badge>
                        {!p.has_source && (
                          <span className="ml-2 text-xs text-amber-600 dark:text-amber-400">
                            нет источника
                          </span>
                        )}
                      </TableCell>
                      {isAdmin && (
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant={p.enabled ? 'outline' : 'default'}
                            disabled={actionLoading || (!p.has_source && !p.enabled)}
                            onClick={() => onToggle(p.filename, !p.enabled, p.name)}
                          >
                            {p.enabled ? 'Отключить' : 'Включить'}
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    </StatusPanel>
  )
}
