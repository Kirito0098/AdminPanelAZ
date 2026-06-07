import { useEffect, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import { ApiError, applyNodeUpdate, checkNodeUpdates } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useNotifications } from '@/context/NotificationContext'
import type { Node } from '@/types'

type GitStatus = {
  updates_available?: boolean
  commits_behind?: number
  local_hash?: string
  remote_hash?: string
  error?: string
}

type Props = {
  node: Node | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onComplete?: () => void
}

function GitBlock({ title, info }: { title: string; info: GitStatus | null }) {
  if (!info) return null
  return (
    <div className="rounded-md border p-3 text-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="font-medium">{title}</span>
        {info.error ? (
          <Badge variant="destructive">ошибка</Badge>
        ) : info.updates_available ? (
          <Badge variant="destructive">{info.commits_behind ?? '?'} коммит(ов)</Badge>
        ) : (
          <Badge variant="secondary">актуально</Badge>
        )}
      </div>
      <div className="grid gap-1 text-xs text-muted-foreground">
        <div>Локальный: {info.local_hash || '—'}</div>
        <div>Удалённый: {info.remote_hash || '—'}</div>
        {info.error && <div className="text-destructive">{info.error}</div>}
      </div>
    </div>
  )
}

export default function NodeUpdateDialog({ node, open, onOpenChange, onComplete }: Props) {
  const { success, error: notifyError } = useNotifications()
  const [agentInfo, setAgentInfo] = useState<GitStatus | null>(null)
  const [antizapretInfo, setAntizapretInfo] = useState<GitStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [scope, setScope] = useState<'all' | 'agent' | 'antizapret'>('all')

  const meta = node?.metadata ?? {}
  const agentVersion = typeof meta.agent_version === 'string' ? meta.agent_version : '—'
  const antizapretVersion = typeof meta.antizapret_version === 'string' ? meta.antizapret_version : '—'

  const load = async () => {
    if (!node) return
    setLoading(true)
    try {
      const res = await checkNodeUpdates(node.id)
      setAgentInfo(res.agent as GitStatus)
      setAntizapretInfo(res.antizapret as GitStatus)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка проверки обновлений')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open && node) {
      setScope('all')
      load()
    }
  }, [open, node?.id])

  const hasUpdates =
    Boolean(agentInfo?.updates_available) || Boolean(antizapretInfo?.updates_available)

  const handleUpdate = async () => {
    if (!node) return
    const scopeLabel =
      scope === 'all' ? 'node agent и AntiZapret' : scope === 'agent' ? 'node agent' : 'AntiZapret'
    if (!confirm(`Обновить ${scopeLabel} на узле «${node.name}»?`)) return

    setUpdating(true)
    try {
      const res = await applyNodeUpdate(node.id, { scope, run_doall: true })
      success(res.message || 'Обновление выполнено')
      if (res.restarting) {
        notifyError('Node agent перезапускается — подождите и выполните проверку здоровья')
      }
      onOpenChange(false)
      onComplete?.()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка обновления')
    } finally {
      setUpdating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download size={18} />
            Обновление узла
          </DialogTitle>
          <DialogDescription>
            {node ? `Узел «${node.name}» — git pull для node agent и/или AntiZapret` : ''}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-2 text-sm md:grid-cols-2">
            <div>Agent: {agentVersion}</div>
            <div>AntiZapret: {antizapretVersion}</div>
          </div>

          <div className="grid gap-2">
            <Label>Что обновлять</Label>
            <Select value={scope} onValueChange={(v) => setScope(v as typeof scope)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Всё (agent + AntiZapret)</SelectItem>
                <SelectItem value="agent">Только node agent</SelectItem>
                <SelectItem value="antizapret">Только AntiZapret</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <GitBlock title="Node agent (AdminPanelAZ)" info={agentInfo} />
            <GitBlock title="AntiZapret" info={antizapretInfo} />
          </div>
        </div>

        <DialogFooter className="gap-2 sm:justify-between">
          <Button variant="outline" onClick={load} disabled={loading || updating}>
            <RefreshCw size={16} />
            {loading ? 'Проверка...' : 'Проверить'}
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Закрыть
            </Button>
            <Button onClick={handleUpdate} disabled={updating || loading || !hasUpdates}>
              {updating ? 'Обновление...' : 'Применить'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
