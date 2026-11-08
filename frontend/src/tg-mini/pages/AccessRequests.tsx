import { useCallback, useEffect, useState } from 'react'
import { Check, Loader2, MessageSquare, ReceiptText, X } from 'lucide-react'
import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import MiniPlanFields from '@/tg-mini/components/MiniPlanFields'
import {
  approveTgRequest,
  getTgNodes,
  getTgRequestReceipt,
  getTgRequestsCount,
  listTgPresets,
  listTgRequests,
  rejectTgRequest,
} from '@/tg-mini/api'
import { formatDateTime } from '@/lib/datetime'
import { selectablePlanNodes } from '@/tg-mini/lib/planNodes'
import type { AccessRequestResponse, PresetResponse, TgMiniNode } from '@/types'

const TYPE_LABELS: Record<string, string> = {
  new_user: 'Новый клиент',
  add_config: 'Ещё конфиг',
  extend_access: 'Продление',
}

function requestTitle(request: AccessRequestResponse): string {
  const who =
    request.telegram_username != null
      ? `@${request.telegram_username}`
      : request.telegram_name || `TG ${request.telegram_id}`
  return `${TYPE_LABELS[request.request_type] ?? request.request_type} · ${who}`
}

/** Admin «Подтверждение доступа» — заявки: одобрить/отклонить. */
export default function AccessRequests() {
  const [requests, setRequests] = useState<AccessRequestResponse[]>([])
  const [pendingCount, setPendingCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [approveTarget, setApproveTarget] = useState<AccessRequestResponse | null>(null)
  const [rejectTarget, setRejectTarget] = useState<AccessRequestResponse | null>(null)
  const [receiptUrl, setReceiptUrl] = useState<string | null>(null)
  const [receiptLoading, setReceiptLoading] = useState(false)
  const [receiptError, setReceiptError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [list, count] = await Promise.all([
        listTgRequests({ status: 'pending', limit: 100 }),
        getTgRequestsCount('pending'),
      ])
      setRequests(list)
      setPendingCount(count)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const runApprove = async (request: AccessRequestResponse, data: Parameters<typeof approveTgRequest>[1]) => {
    setBusyId(request.id)
    setError(null)
    try {
      await approveTgRequest(request.id, data)
      setApproveTarget(null)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка одобрения')
    } finally {
      setBusyId(null)
    }
  }

  const runReject = async (request: AccessRequestResponse, reason: string | null) => {
    setBusyId(request.id)
    setError(null)
    try {
      await rejectTgRequest(request.id, { reason })
      setRejectTarget(null)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка отклонения')
    } finally {
      setBusyId(null)
    }
  }

  const openReceipt = async (request: AccessRequestResponse) => {
    setReceiptLoading(true)
    setReceiptError(null)
    setReceiptUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
    try {
      const blob = await getTgRequestReceipt(request.id)
      setReceiptUrl(URL.createObjectURL(blob))
    } catch (err) {
      setReceiptError(err instanceof ApiError ? err.message : 'Не удалось загрузить чек')
    } finally {
      setReceiptLoading(false)
    }
  }

  const closeReceipt = () => {
    setReceiptUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
    setReceiptError(null)
  }

  const approveOneTap = (request: AccessRequestResponse) => {
    if (request.request_type === 'add_config') {
      void runApprove(request, { count: Math.max(1, request.requested_count || 1) })
    } else if (request.request_type === 'extend_access') {
      void runApprove(request, { days: 30 })
    }
  }

  return (
    <div className="tg-mini-dashboard space-y-3">
      <MiniPageHeader
        title="Подтверждение доступа"
        subtitle={`${pendingCount} ожидает решения`}
        onRefresh={() => void load()}
        refreshing={loading}
      />

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading && requests.length === 0 ? (
        <div className="tg-mini-skeleton tg-mini-skeleton-section" aria-busy="true" />
      ) : requests.length === 0 ? (
        <div className="tg-mini-filter-empty">
          <MessageSquare size={22} className="text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">Нет заявок</p>
          <p className="text-xs text-muted-foreground">Новые заявки появятся здесь</p>
        </div>
      ) : (
        requests.map((request) => {
          const busy = busyId === request.id
          const oneTap = request.request_type !== 'new_user'
          return (
            <Card key={request.id} className="tg-mini-config-card">
              <CardContent className="space-y-2 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 space-y-1">
                    <p className="truncate text-sm font-medium">{requestTitle(request)}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatDateTime(request.created_at)}
                      {request.requested_count > 1 ? ` · конфигов: ${request.requested_count}` : ''}
                    </p>
                    {request.user_note && (
                      <p className="text-xs text-muted-foreground">{request.user_note}</p>
                    )}
                  </div>
                  <Badge variant="secondary" className="shrink-0 text-[10px]">
                    {TYPE_LABELS[request.request_type] ?? request.request_type}
                  </Badge>
                </div>

                {request.receipt_file_id && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="w-full gap-1.5"
                    disabled={receiptLoading}
                    onClick={() => void openReceipt(request)}
                  >
                    {receiptLoading ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <ReceiptText size={14} />
                    )}
                    Посмотреть чек
                  </Button>
                )}

                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    className="flex-1 gap-1.5"
                    disabled={busy}
                    onClick={() =>
                      oneTap ? approveOneTap(request) : setApproveTarget(request)
                    }
                  >
                    {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                    Одобрить
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="flex-1 gap-1.5"
                    disabled={busy}
                    onClick={() => setRejectTarget(request)}
                  >
                    <X size={14} /> Отклонить
                  </Button>
                </div>
              </CardContent>
            </Card>
          )
        })
      )}

      {approveTarget && (
        <ApproveNewUserDialog
          request={approveTarget}
          busy={busyId === approveTarget.id}
          onClose={() => setApproveTarget(null)}
          onSubmit={(data) => void runApprove(approveTarget, data)}
        />
      )}

      <RejectDialog
        request={rejectTarget}
        busy={busyId === rejectTarget?.id}
        onClose={() => setRejectTarget(null)}
        onSubmit={(reason) => rejectTarget && void runReject(rejectTarget, reason)}
      />

      <Dialog
        open={Boolean(receiptUrl) || receiptLoading || Boolean(receiptError)}
        onOpenChange={(open) => !open && closeReceipt()}
      >
        <DialogContent className="max-w-md">
          <DialogTitle>Чек оплаты</DialogTitle>
          {receiptLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
          {receiptError && <p className="text-sm text-destructive">{receiptError}</p>}
          {receiptUrl && (
            <img
              src={receiptUrl}
              alt="Чек оплаты заявки"
              className="max-h-[70vh] w-full rounded-md object-contain"
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function ApproveNewUserDialog({
  request,
  busy,
  onClose,
  onSubmit,
}: {
  request: AccessRequestResponse
  busy: boolean
  onClose: () => void
  onSubmit: (data: { preset_id?: number; username?: string; node_ids?: number[]; protocols?: string[]; config_count?: number }) => void
}) {
  const [username, setUsername] = useState('')
  const [presets, setPresets] = useState<PresetResponse[]>([])
  const [presetId, setPresetId] = useState('')
  const [nodes, setNodes] = useState<TgMiniNode[]>([])
  const [nodeIds, setNodeIds] = useState<number[]>([])
  const [protocols, setProtocols] = useState<string[]>(['openvpn', 'wireguard'])
  const [count, setCount] = useState('1')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setUsername(request.telegram_username || `tg_${request.telegram_id}`)
    void listTgPresets().then(setPresets).catch(() => setPresets([]))
    void getTgNodes()
      .then((data) => {
        const available = selectablePlanNodes(data.nodes)
        setNodes(available)
        setNodeIds(available.filter((node) => node.is_active).map((node) => node.id))
      })
      .catch(() => setNodes([]))
  }, [request])

  const preset = presets.find((item) => String(item.id) === presetId)

  const submit = () => {
    const name = username.trim()
    if (!name) {
      setError('Укажите логин')
      return
    }
    if (preset) {
      onSubmit({ preset_id: preset.id, username: name })
      return
    }
    if (nodeIds.length === 0 || protocols.length === 0) {
      setError('Выберите узлы и протоколы')
      return
    }
    onSubmit({
      username: name,
      node_ids: nodeIds,
      protocols,
      config_count: Math.max(1, Number.parseInt(count, 10) || 1),
    })
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle>Одобрить нового клиента</DialogTitle>
        <DialogDescription>{requestTitle(request)}</DialogDescription>

        <div className="space-y-3 pt-2">
          <div className="space-y-1.5">
            <Label htmlFor="approve-username">Логин</Label>
            <Input
              id="approve-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="off"
            />
          </div>

          {presets.length > 0 && (
            <div className="space-y-1.5">
              <Label htmlFor="approve-preset">Пресет</Label>
              <select
                id="approve-preset"
                value={presetId}
                onChange={(e) => setPresetId(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm"
              >
                <option value="">Вручную</option>
                {presets.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {!preset && (
            <MiniPlanFields
              idPrefix="approve"
              nodes={nodes}
              nodeIds={nodeIds}
              onNodeIdsChange={setNodeIds}
              protocols={protocols}
              onProtocolsChange={setProtocols}
              count={count}
              onCountChange={setCount}
            />
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button type="button" className="w-full" disabled={busy} onClick={submit}>
            {busy ? <Loader2 size={16} className="animate-spin" /> : 'Одобрить'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function RejectDialog({
  request,
  busy,
  onClose,
  onSubmit,
}: {
  request: AccessRequestResponse | null
  busy: boolean
  onClose: () => void
  onSubmit: (reason: string | null) => void
}) {
  const [reason, setReason] = useState('')

  useEffect(() => {
    setReason('')
  }, [request])

  return (
    <Dialog open={Boolean(request)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle>Отклонить заявку</DialogTitle>
        <DialogDescription>{request ? requestTitle(request) : ''}</DialogDescription>
        <div className="space-y-3 pt-2">
          <div className="space-y-1.5">
            <Label htmlFor="reject-reason">Причина (необязательно)</Label>
            <Input id="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <Button
            type="button"
            variant="destructive"
            className="w-full"
            disabled={busy}
            onClick={() => onSubmit(reason.trim() || null)}
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : 'Отклонить'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
