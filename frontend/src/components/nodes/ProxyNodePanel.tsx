import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, Loader2, RefreshCw, Save } from 'lucide-react'
import {
  ApiError,
  getProxyNodeStatus,
  putProxyDestination,
  putProxyNodeStatus,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'
import type { Node, ProxyStatusResponse } from '@/types'

/** AntiZapret upstream docs — admin installs proxy.sh manually; panel never does. */
export const AZ_PROXY_SH_DOCS_URL =
  'https://github.com/GubernievS/AntiZapret-VPN#настроить-прокси-сервер'

type ProxyNodePanelProps = {
  node: Node
  onUpdated?: () => void | Promise<void>
}

export default function ProxyNodePanel({ node, onUpdated }: ProxyNodePanelProps) {
  const { success, error: notifyError } = useNotifications()
  const [status, setStatus] = useState<ProxyStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [destination, setDestination] = useState(node.destination_ip ?? '')

  const applyStatus = useCallback((payload: ProxyStatusResponse) => {
    setStatus(payload)
    if (payload.destination_ip != null) {
      setDestination(payload.destination_ip)
    }
  }, [])

  const loadStatus = useCallback(async () => {
    setLoading(true)
    try {
      applyStatus(await getProxyNodeStatus(node.id))
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось получить статус прокси')
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }, [applyStatus, node.id, notifyError])

  useEffect(() => {
    void loadStatus()
  }, [loadStatus])

  const handleRefresh = async () => {
    setLoading(true)
    try {
      applyStatus(await putProxyNodeStatus(node.id))
      await onUpdated?.()
      success('Статус прокси обновлён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось обновить статус')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveDestination = async () => {
    const trimmed = destination.trim()
    if (!trimmed) {
      notifyError('Укажите DESTINATION IP')
      return
    }
    setSaving(true)
    try {
      applyStatus(await putProxyDestination(node.id, trimmed))
      await onUpdated?.()
      success('DESTINATION обновлён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить DESTINATION')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-amber-500/25 bg-amber-500/5 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium">Прокси (proxy_agent)</p>
          {status && (
            <Badge variant={status.installed ? 'default' : 'secondary'} className="text-[10px]">
              {status.installed ? 'proxy.sh обнаружен' : 'proxy.sh не найден'}
            </Badge>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={loading || saving}
          onClick={() => void handleRefresh()}
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Статус
        </Button>
      </div>

      {loading && !status ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 size={14} className="animate-spin" />
          Загрузка статуса…
        </p>
      ) : (
        <>
          {status && !status.installed && (
            <SettingsAlert variant="warning" title="proxy.sh не установлен на этом сервере">
              Установите прокси сами по инструкции AntiZapret, затем обновите статус. Панель не
              ставит и не запускает proxy.sh.{' '}
              <a
                href={AZ_PROXY_SH_DOCS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-medium underline underline-offset-2"
              >
                Настроить прокси-сервер
                <ExternalLink size={12} />
              </a>
            </SettingsAlert>
          )}

          {status?.detail && (
            <p className="text-xs text-muted-foreground">{status.detail}</p>
          )}

          <div className="grid gap-2">
            <Label htmlFor={`proxy-dest-${node.id}`}>DESTINATION IP</Label>
            <div className="flex flex-wrap gap-2">
              <Input
                id={`proxy-dest-${node.id}`}
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="x.x.x.x"
                className="font-mono text-xs"
                disabled={saving}
              />
              <Button
                type="button"
                size="sm"
                disabled={saving || loading}
                onClick={() => void handleSaveDestination()}
              >
                {saving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Save size={14} />
                )}
                Сохранить
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Меняет целевой IP в iptables DNAT/SNAT на RU-прокси (не через proxy.sh).
            </p>
          </div>

          {(node.destination_ip || status?.destination_ip) && (
            <p className="font-mono text-[11px] text-muted-foreground">
              Кэш панели: {node.destination_ip ?? status?.destination_ip ?? '—'}
            </p>
          )}
        </>
      )}
    </div>
  )
}
