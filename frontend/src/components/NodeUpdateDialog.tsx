import { useEffect, useState } from 'react'
import { Download, GitBranch, Loader2, RefreshCw } from 'lucide-react'
import { ApiError, applyNodeUpdate, checkNodeUpdates } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useNotifications } from '@/context/NotificationContext'
import type { Node } from '@/types'

type GitStatus = {
  updates_available?: boolean
  commits_behind?: number
  commits_ahead?: number
  diverged?: boolean
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
    <Card className="shadow-none">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <GitBranch size={14} />
            {title}
          </CardTitle>
          {info.error ? (
            <Badge variant="destructive">ошибка</Badge>
          ) : info.updates_available ? (
            <Badge variant="destructive">{info.commits_behind ?? '?'} коммит(ов)</Badge>
          ) : (
            <Badge variant="success">актуально</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        <div className="grid gap-2 rounded-md border bg-muted/30 p-3 text-xs">
          <div>
            <span className="text-muted-foreground">Локальный: </span>
            <code className="font-mono">{info.local_hash || '—'}</code>
          </div>
          <div>
            <span className="text-muted-foreground">Удалённый: </span>
            <code className="font-mono">{info.remote_hash || '—'}</code>
          </div>
        </div>
        {info.diverged && !info.error && (
          <p className="text-xs text-amber-700 dark:text-amber-300">
            История расходится с GitHub (часто после squash или force push). Обновление выполнит{' '}
            <code className="font-mono">git reset --hard origin/main</code>, если на узле нет локальных
            изменений.
          </p>
        )}
        {info.error && <p className="text-xs text-destructive">{info.error}</p>}
      </CardContent>
    </Card>
  )
}

export default function NodeUpdateDialog({ node, open, onOpenChange, onComplete }: Props) {
  const { success, error: notifyError } = useNotifications()
  const [agentInfo, setAgentInfo] = useState<GitStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  const meta = node?.metadata ?? {}
  const agentVersion = typeof meta.agent_version === 'string' ? meta.agent_version : '—'

  const load = async () => {
    if (!node) return
    setLoading(true)
    try {
      const res = await checkNodeUpdates(node.id)
      setAgentInfo(res.agent as GitStatus)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка проверки обновлений')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open && node) {
      setShowConfirm(false)
      setAgentInfo(null)
      load()
    }
  }, [open, node?.id])

  const hasUpdates = Boolean(agentInfo?.updates_available)

  const handleUpdate = async () => {
    if (!node) return
    setUpdating(true)
    try {
      const res = await applyNodeUpdate(node.id)
      success(res.message || 'Обновление выполнено')
      if (res.restarting) {
        notifyError('Node agent перезапускается — подождите и выполните проверку здоровья')
      }
      setShowConfirm(false)
      handleOpenChange(false)
      onComplete?.()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка обновления')
    } finally {
      setUpdating(false)
    }
  }

  const handleOpenChange = (next: boolean) => {
    if (!next && (updating || loading)) return
    onOpenChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download size={18} />
            Обновление узла
          </DialogTitle>
          <DialogDescription>
            {node ? `Узел «${node.name}» — git pull для node agent` : ''}
          </DialogDescription>
        </DialogHeader>

        {loading && !agentInfo ? (
          <Spinner label="Проверка обновлений..." className="py-8" />
        ) : (
          <div className="space-y-4">
            <InlineProgressBar active={updating} label="Обновление узла..." />
            <div className="rounded-md border bg-muted/30 p-4 text-sm">
              <span className="text-muted-foreground">Agent: </span>
              <span className="font-mono text-xs">{agentVersion}</span>
            </div>

            <GitBlock title="Node agent (AdminPanelAZ)" info={agentInfo} />

            {!hasUpdates && !loading && agentInfo && (
              <SettingsAlert variant="info">Обновления не найдены — репозиторий актуален</SettingsAlert>
            )}

            {showConfirm && hasUpdates && (
              <SettingsAlert variant="warning" title="Подтвердите обновление">
                Будет выполнен git pull для node agent на узле «{node?.name}». Node agent может перезапуститься —
                выполните проверку здоровья после завершения.
              </SettingsAlert>
            )}
          </div>
        )}

        <DialogFooter className="gap-2 sm:justify-between">
          <Button type="button" variant="outline" onClick={load} disabled={loading || updating}>
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Проверка...' : 'Проверить'}
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={updating}>
              Закрыть
            </Button>
            {!showConfirm ? (
              <Button type="button" onClick={() => setShowConfirm(true)} disabled={updating || loading || !hasUpdates}>
                Применить
              </Button>
            ) : (
              <Button type="button" onClick={handleUpdate} disabled={updating || loading} variant="destructive">
                {updating ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Обновление...
                  </>
                ) : (
                  'Подтвердить'
                )}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
