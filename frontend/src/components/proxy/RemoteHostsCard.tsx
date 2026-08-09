import {
  ApiError,
  allowFirstRemoteHost,
  getNodeRemoteHosts,
  putNodeRemoteHosts,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useNotifications } from '@/context/NotificationContext'
import { useHaReplicaReadonly } from '@/hooks/useHaReplicaReadonly'
import { AZ_PROXY_SH_DOCS_URL } from '@/components/nodes/ProxyNodePanel'
import { ArrowDown, ArrowUp, Cable, Plus, RefreshCw, Save, Shield, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

export const MAX_REMOTE_HOSTS = 8

export function firstNonEmptyRemoteHost(hosts: string[]): string | undefined {
  return hosts.find((host) => host.trim().length > 0)
}

export type RemoteHostsCardProps = {
  nodeId: number | null
  disabled?: boolean
  /** Standalone card vs list block embedded in AntiZapret «OpenVPN (панель)». */
  variant?: 'card' | 'embedded'
  className?: string
  id?: string
  /** Fired after successful load or save with the persisted hosts list. */
  onSavedHostsChange?: (hosts: string[]) => void
  /** Fired when draft vs saved dirty state changes. */
  onDirtyChange?: (dirty: boolean) => void
  /** Fired only after a successful save (for syncing OPENVPN_HOST in AntiZapret). */
  onHostsPersisted?: (hosts: string[]) => void
}

function RemoteHostsListBody({
  nodeId,
  disabled,
  remoteHosts,
  savedRemoteHosts,
  remoteHostsDirty,
  remoteHostsSaving,
  remoteHostsLoadError,
  allowFirstBusy,
  onRetry,
  onRemoteHostsChange,
  onSave,
  onAllowFirst,
}: {
  nodeId: number | null
  disabled: boolean
  remoteHosts: string[]
  savedRemoteHosts: string[]
  remoteHostsDirty: boolean
  remoteHostsSaving: boolean
  remoteHostsLoadError: string | null
  allowFirstBusy: boolean
  onRetry: () => void
  onRemoteHostsChange: (hosts: string[]) => void
  onSave: () => void
  onAllowFirst: () => void
}) {
  const listDisabled = disabled || remoteHostsSaving || nodeId == null || remoteHostsLoadError != null
  const canAdd = remoteHosts.length < MAX_REMOTE_HOSTS
  const canAllowFirst =
    !listDisabled && !allowFirstBusy && savedRemoteHosts.length > 0 && !remoteHostsDirty

  const moveHost = (index: number, delta: number) => {
    const next = index + delta
    if (next < 0 || next >= remoteHosts.length) return
    const updated = [...remoteHosts]
    const [item] = updated.splice(index, 1)
    updated.splice(next, 0, item)
    onRemoteHostsChange(updated)
  }

  if (nodeId == null) {
    return (
      <SettingsAlert variant="warning" title="Нет активного узла">
        Выберите активный узел, чтобы редактировать список адресов подключения.
      </SettingsAlert>
    )
  }

  if (remoteHostsLoadError != null) {
    return (
      <div className="space-y-3">
        <SettingsAlert variant="danger" title="Не удалось загрузить адреса">
          {remoteHostsLoadError}
        </SettingsAlert>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={disabled || remoteHostsSaving}
          onClick={onRetry}
        >
          <RefreshCw className="mr-1.5 h-4 w-4" />
          Повторить загрузку адресов
        </Button>
      </div>
    )
  }

  return (
    <>
      <div className="space-y-1">
        <h3 className="text-sm font-medium">Список remote OpenVPN</h3>
        <p className="text-xs text-muted-foreground">
          Упорядоченный список адресов в клиентских .ovpn (до {MAX_REMOTE_HOSTS}). Сохраняется
          отдельно от остальных параметров setup.
        </p>
      </div>

      <ul className="list-disc space-y-1.5 pl-5 text-xs leading-relaxed text-muted-foreground">
        <li>Порядок сверху вниз — порядок попыток OpenVPN.</li>
        <li>Адресов сколько нужно (до {MAX_REMOTE_HOSTS}); схема у каждого админа своя.</li>
        <li>
          Российский прокси ставится отдельно скриптом AntiZapret (
          <a
            href={AZ_PROXY_SH_DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-primary underline-offset-4 hover:underline"
          >
            инструкция
          </a>
          ); панель его не устанавливает и не запускает.
        </li>
        <li>Один proxy.sh направляет на один зарубежный сервер.</li>
        <li>Список хранится в панели и не пропадает при обновлении AntiZapret.</li>
        <li>
          IP прокси обычно добавляют в allow-ips.txt на VPN-сервере (кнопка ниже — только первый
          адрес списка; панель не ставит proxy.sh).
        </li>
        <li>
          Трафик считается на зарубежном VPN, куда подключились; прокси в статистике панели
          отдельно не учитывается.
        </li>
      </ul>

      <div className="space-y-2">
        {remoteHosts.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Список пуст — в .ovpn останутся remote из файла AntiZapret без патча.
          </p>
        )}
        {remoteHosts.map((host, index) => (
          <div key={`remote-host-${index}`} className="flex items-center gap-2">
            <span className="w-5 shrink-0 text-center font-mono text-[10px] text-muted-foreground">
              {index + 1}
            </span>
            <Input
              value={host}
              disabled={listDisabled}
              placeholder="IP или домен"
              aria-label={`Адрес ${index + 1}`}
              onChange={(e) => {
                const updated = [...remoteHosts]
                updated[index] = e.target.value
                onRemoteHostsChange(updated)
              }}
            />
            <div className="flex shrink-0 gap-1">
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-9 w-9"
                disabled={listDisabled || index === 0}
                aria-label="Переместить вверх"
                onClick={() => moveHost(index, -1)}
              >
                <ArrowUp className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-9 w-9"
                disabled={listDisabled || index >= remoteHosts.length - 1}
                aria-label="Переместить вниз"
                onClick={() => moveHost(index, 1)}
              >
                <ArrowDown className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-9 w-9"
                disabled={listDisabled}
                aria-label="Удалить адрес"
                onClick={() => onRemoteHostsChange(remoteHosts.filter((_, i) => i !== index))}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={listDisabled || !canAdd}
          onClick={() => onRemoteHostsChange([...remoteHosts, ''])}
        >
          <Plus className="mr-1.5 h-4 w-4" />
          Добавить адрес
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={listDisabled || !remoteHostsDirty}
          onClick={onSave}
        >
          <Save className="mr-1.5 h-4 w-4" />
          {remoteHostsSaving ? 'Сохранение...' : 'Сохранить адреса'}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canAllowFirst}
          onClick={onAllowFirst}
          title={
            savedRemoteHosts.length === 0
              ? 'Сначала сохраните хотя бы один адрес'
              : remoteHostsDirty
                ? 'Сначала сохраните изменения списка'
                : 'Добавить первый адрес списка в allow-ips.txt на VPN-узле'
          }
        >
          <Shield className="mr-1.5 h-4 w-4" />
          {allowFirstBusy ? 'Добавление в allow-ips...' : 'Добавить первый адрес в allow-ips'}
        </Button>
      </div>
    </>
  )
}

export default function RemoteHostsCard({
  nodeId,
  disabled = false,
  variant = 'card',
  className,
  id,
  onSavedHostsChange,
  onDirtyChange,
  onHostsPersisted,
}: RemoteHostsCardProps) {
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
  const haReplicaReadonly = useHaReplicaReadonly()
  const controlsDisabled = disabled || haReplicaReadonly

  const [remoteHosts, setRemoteHosts] = useState<string[]>([])
  const [savedRemoteHosts, setSavedRemoteHosts] = useState<string[]>([])
  const [remoteHostsSaving, setRemoteHostsSaving] = useState(false)
  const [allowFirstBusy, setAllowFirstBusy] = useState(false)
  const [remoteHostsLoadError, setRemoteHostsLoadError] = useState<string | null>(null)
  const loadedNodeIdRef = useRef<number | null>(null)
  const onSavedHostsChangeRef = useRef(onSavedHostsChange)
  const onDirtyChangeRef = useRef(onDirtyChange)
  const onHostsPersistedRef = useRef(onHostsPersisted)

  useEffect(() => {
    onSavedHostsChangeRef.current = onSavedHostsChange
  }, [onSavedHostsChange])
  useEffect(() => {
    onDirtyChangeRef.current = onDirtyChange
  }, [onDirtyChange])
  useEffect(() => {
    onHostsPersistedRef.current = onHostsPersisted
  }, [onHostsPersisted])

  const remoteHostsDirty = useMemo(
    () =>
      remoteHostsLoadError == null &&
      JSON.stringify(remoteHosts) !== JSON.stringify(savedRemoteHosts),
    [remoteHosts, savedRemoteHosts, remoteHostsLoadError],
  )

  useEffect(() => {
    onDirtyChangeRef.current?.(remoteHostsDirty)
  }, [remoteHostsDirty])

  const loadRemoteHosts = useCallback(
    async (idToLoad: number) => {
      if (loadedNodeIdRef.current !== idToLoad) {
        setRemoteHosts([])
        setSavedRemoteHosts([])
        loadedNodeIdRef.current = null
        onSavedHostsChangeRef.current?.([])
      }
      try {
        const hostsResp = await getNodeRemoteHosts(idToLoad)
        setRemoteHosts(hostsResp.hosts)
        setSavedRemoteHosts(hostsResp.hosts)
        loadedNodeIdRef.current = idToLoad
        setRemoteHostsLoadError(null)
        onSavedHostsChangeRef.current?.(hostsResp.hosts)
        return true
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : 'Не удалось загрузить адреса подключения'
        setRemoteHostsLoadError(message)
        notifyError(message)
        if (loadedNodeIdRef.current !== idToLoad) {
          setRemoteHosts([])
          setSavedRemoteHosts([])
          onSavedHostsChangeRef.current?.([])
        }
        return false
      }
    },
    [notifyError],
  )

  useEffect(() => {
    if (nodeId == null) {
      setRemoteHosts([])
      setSavedRemoteHosts([])
      loadedNodeIdRef.current = null
      setRemoteHostsLoadError(null)
      onSavedHostsChangeRef.current?.([])
      return
    }
    void loadRemoteHosts(nodeId)
  }, [nodeId, loadRemoteHosts])

  const saveRemoteHosts = useCallback(async () => {
    if (nodeId == null) {
      notifyError('Нет активного узла для сохранения адресов')
      return
    }
    if (remoteHostsLoadError != null) {
      notifyError('Сначала загрузите список адресов')
      return
    }
    setRemoteHostsSaving(true)
    try {
      const result = await putNodeRemoteHosts(nodeId, remoteHosts)
      setRemoteHosts(result.hosts)
      setSavedRemoteHosts(result.hosts)
      loadedNodeIdRef.current = nodeId
      setRemoteHostsLoadError(null)
      onSavedHostsChangeRef.current?.(result.hosts)
      onHostsPersistedRef.current?.(result.hosts)
      success('Адреса подключения сохранены')
      for (const w of result.warnings ?? []) {
        notifyWarning(w)
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения адресов')
    } finally {
      setRemoteHostsSaving(false)
    }
  }, [nodeId, remoteHosts, remoteHostsLoadError, notifyError, notifyWarning, success])

  const allowFirst = useCallback(async () => {
    if (nodeId == null) {
      notifyError('Нет активного узла')
      return
    }
    if (savedRemoteHosts.length === 0) {
      notifyError('Сначала задайте и сохраните адреса подключения')
      return
    }
    if (remoteHostsDirty) {
      notifyError('Сначала сохраните изменения списка адресов')
      return
    }
    setAllowFirstBusy(true)
    try {
      const result = await allowFirstRemoteHost(nodeId)
      if (result.added) {
        success(`Адрес ${result.host} добавлен в allow-ips.txt`)
      } else {
        notifyWarning(
          result.detail ? `${result.host}: ${result.detail}` : `${result.host} уже есть в allow-ips`,
        )
      }
      for (const w of result.warnings ?? []) {
        notifyWarning(w)
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось добавить адрес в allow-ips')
    } finally {
      setAllowFirstBusy(false)
    }
  }, [
    nodeId,
    savedRemoteHosts.length,
    remoteHostsDirty,
    notifyError,
    notifyWarning,
    success,
  ])

  const listProps = {
    nodeId,
    disabled: controlsDisabled,
    remoteHosts,
    savedRemoteHosts,
    remoteHostsDirty,
    remoteHostsSaving,
    remoteHostsLoadError,
    allowFirstBusy,
    onRetry: () => {
      if (nodeId != null) void loadRemoteHosts(nodeId)
    },
    onRemoteHostsChange: setRemoteHosts,
    onSave: () => void saveRemoteHosts(),
    onAllowFirst: () => void allowFirst(),
  }

  if (variant === 'embedded') {
    return (
      <div id={id} className={`space-y-4 ${className ?? ''}`.trim()}>
        <RemoteHostsListBody {...listProps} />
      </div>
    )
  }

  return (
    <Card id={id} className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Cable className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <CardTitle className="text-base">Адреса подключения</CardTitle>
              <CardDescription className="mt-1">
                Список remote OpenVPN для активного VPN-узла. Нельзя совпадать с доменом панели.
              </CardDescription>
            </div>
          </div>
          {remoteHostsDirty && (
            <Badge
              variant="outline"
              className="shrink-0 border-amber-500/40 px-1.5 py-0 text-[10px] text-amber-700 dark:text-amber-300"
            >
              адреса не сохранены
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <RemoteHostsListBody {...listProps} />
      </CardContent>
    </Card>
  )
}
