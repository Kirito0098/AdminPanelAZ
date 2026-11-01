import {
  ApiError,
  getNodeOpenVpnMultihome,
  putNodeOpenVpnMultihome,
} from '@/api/client'
import RemoteHostsCard from '@/components/proxy/RemoteHostsCard'
import DnsAaaaCard from '@/components/routing/DnsAaaaCard'
import DnsServersCard from '@/components/routing/DnsServersCard'
import OpenVpnTuningCard from '@/components/routing/OpenVpnTuningCard'
import OpenVpnBufferGuardCard from '@/components/routing/OpenVpnBufferGuardCard'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { SettingsToolbar } from '@/components/settings/SettingsChrome'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import { Cable, RefreshCw, Server } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

function SectionHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-col gap-0.5 border-b pb-2">
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  )
}

function OpenVpnMultihomeToggle({
  nodeId,
  disabled,
}: {
  nodeId: number | null
  disabled: boolean
}) {
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
  const [enabled, setEnabled] = useState(false)
  const [onDisk, setOnDisk] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [restoring, setRestoring] = useState(false)
  const autoRestoreAttempted = useRef<number | null>(null)

  const applyState = useCallback(
    (data: { enabled: boolean; on_disk?: boolean | null; warnings?: string[] }) => {
      setEnabled(Boolean(data.enabled))
      setOnDisk(typeof data.on_disk === 'boolean' ? data.on_disk : null)
      if (data.warnings?.length) {
        notifyWarning(data.warnings.join('; '))
      }
    },
    [notifyWarning],
  )

  const restoreToDisk = useCallback(async () => {
    if (nodeId == null || saving || disabled || restoring) return
    setRestoring(true)
    try {
      const data = await putNodeOpenVpnMultihome(nodeId, true)
      applyState(data)
      if (!data.warnings?.length) {
        success('OpenVPN multihome восстановлен на диске после setup.sh')
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось восстановить multihome')
    } finally {
      setRestoring(false)
    }
  }, [applyState, disabled, nodeId, notifyError, restoring, saving, success])

  const load = useCallback(async () => {
    if (nodeId == null) {
      setEnabled(false)
      setOnDisk(null)
      setLoadError(null)
      autoRestoreAttempted.current = null
      return
    }
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getNodeOpenVpnMultihome(nodeId)
      applyState(data)
      // After AntiZapret setup.sh server confs are stock again — re-apply from panel DB.
      if (
        Boolean(data.enabled) &&
        data.on_disk === false &&
        !disabled &&
        autoRestoreAttempted.current !== nodeId
      ) {
        autoRestoreAttempted.current = nodeId
        setLoading(false)
        await restoreToDisk()
        return
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Не удалось загрузить multihome'
      setLoadError(message)
    } finally {
      setLoading(false)
    }
  }, [applyState, disabled, nodeId, restoreToDisk])

  useEffect(() => {
    void load()
  }, [load])

  const onToggle = async (checked: boolean) => {
    if (nodeId == null || saving || disabled || restoring) return
    setSaving(true)
    try {
      const data = await putNodeOpenVpnMultihome(nodeId, checked)
      applyState(data)
      if (data.warnings?.length) {
        // warnings already shown in applyState
      } else {
        success(checked ? 'OpenVPN multihome включён' : 'OpenVPN multihome выключен')
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить multihome')
    } finally {
      setSaving(false)
    }
  }

  if (nodeId == null) {
    return (
      <p className="text-xs text-muted-foreground">Выберите VPN-узел, чтобы настроить multihome.</p>
    )
  }

  const busy = disabled || loading || saving || restoring

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Label htmlFor="openvpn-multihome" className="font-medium leading-snug">
              OpenVPN multihome (несколько IP на сервере)
            </Label>
            {onDisk === true && (
              <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
                на диске
              </Badge>
            )}
            {onDisk === false && enabled && (
              <Badge
                variant="outline"
                className="border-amber-500/40 px-1.5 py-0 text-[10px] text-amber-700 dark:text-amber-300"
              >
                не на диске
              </Badge>
            )}
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Нужно при нескольких публичных IPv4. Флаг в БД панели. После{' '}
            <span className="font-mono">setup.sh</span> AntiZapret конфиги на диске снова без{' '}
            <span className="font-mono">multihome</span> — откройте эту страницу (авто-восстановление) или
            нажмите «Восстановить».
          </p>
        </div>
        <Switch
          id="openvpn-multihome"
          checked={enabled}
          disabled={busy || loadError != null}
          className="mt-0.5"
          aria-label={`OpenVPN multihome: ${enabled ? 'включено' : 'выключено'}`}
          onCheckedChange={(checked) => {
            void onToggle(checked)
          }}
        />
      </div>
      {enabled && onDisk === false && !loadError && (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs text-amber-700 dark:text-amber-300">
            После setup.sh директива пропала с диска.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => void restoreToDisk()}
          >
            <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', restoring && 'animate-spin')} />
            Восстановить
          </Button>
        </div>
      )}
      {loadError && (
        <div className="flex flex-wrap items-center gap-2">
          <SettingsAlert variant="danger">{loadError}</SettingsAlert>
          <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void load()}>
            <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', loading && 'animate-spin')} />
            Повторить
          </Button>
        </div>
      )}
    </div>
  )
}

type OpenVpnPanelTabProps = {
  activeNodeId: number | null
  nodeName?: string | null
  disabled?: boolean
  remotesEpoch: number
  remoteHostsDirty: boolean
  onSavedHostsChange: (hosts: string[], applyToWireguard?: boolean) => void
  onDirtyChange: (dirty: boolean) => void
  onHostsPersisted: (hosts: string[], applyToWireguard?: boolean) => void
}

/** Доработки панели: список remote OpenVPN и multihome (не из AntiZapret setup). */
export default function OpenVpnPanelTab({
  activeNodeId,
  nodeName,
  disabled = false,
  remotesEpoch,
  remoteHostsDirty,
  onSavedHostsChange,
  onDirtyChange,
  onHostsPersisted,
}: OpenVpnPanelTabProps) {
  return (
    <div className="space-y-6">
      <SettingsToolbar
        title="OpenVPN (панель)"
        meta={
          <span className="flex flex-wrap items-center gap-2">
            {nodeName && (
              <Badge variant="outline" className="gap-1.5">
                <Server className="h-3 w-3" />
                {nodeName}
              </Badge>
            )}
            <span>Адреса в профилях, multihome, DNS и состояние установки — то, чего нет в файле setup.</span>
          </span>
        }
        actions={
          remoteHostsDirty ? (
            <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-300">
              адреса не сохранены
            </Badge>
          ) : undefined
        }
      />

      <section className="space-y-3">
        <SectionHeading title="Подключение" hint="Что клиент видит в профилях: адреса входа и multihome" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="min-w-0 xl:col-span-2">

      <Card className="overflow-hidden">
        <CardHeader className="pb-3">
          <div className="flex gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Cable className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <CardTitle className="text-base">Список remote OpenVPN</CardTitle>
              <CardDescription className="mt-1">
                Упорядоченный список адресов в клиентских .ovpn. Хранится в БД панели на активном
                узле. Первый адрес — слот входа (прокси, если он есть): при сохранении пишется в
                OPENVPN_HOST.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="border-t px-4 py-4 sm:px-5">
          <RemoteHostsCard
            key={`remotes-${activeNodeId ?? 'none'}-${remotesEpoch}`}
            nodeId={activeNodeId}
            disabled={disabled}
            variant="embedded"
            onSavedHostsChange={onSavedHostsChange}
            onDirtyChange={onDirtyChange}
            onHostsPersisted={onHostsPersisted}
          />
        </CardContent>
      </Card>
          </div>

      <Card className="overflow-hidden">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">OpenVPN multihome</CardTitle>
          <CardDescription className="mt-1">
            Директива <code>multihome</code> в server conf: сервер отвечает клиенту с того же IP, к которому тот
            подключился, поэтому несколько публичных адресов работают без «прыжков» соединения. Флаг хранится в
            панели — после setup.sh конфиги становятся стоковыми, и панель возвращает директиву с этой страницы.
          </CardDescription>
        </CardHeader>
        <CardContent className="border-t px-4 py-4 sm:px-5">
          <OpenVpnMultihomeToggle
            key={`multihome-${activeNodeId ?? 'none'}`}
            nodeId={activeNodeId}
            disabled={disabled}
          />
        </CardContent>
      </Card>
        </div>
      </section>

      <section className="space-y-3">
        <SectionHeading title="DNS" hint="Резолверы AntiZapret и ответ на AAAA-запросы" />
        <div className="grid gap-4 xl:grid-cols-2">
          <DnsServersCard activeNodeId={activeNodeId} disabled={disabled} />
          <DnsAaaaCard activeNodeId={activeNodeId} disabled={disabled} />
        </div>
      </section>

      <section className="space-y-3">
        <SectionHeading
          title="Диагностика и установка"
          hint="Профили, логи, MTU/DCO/патч/протоколы OpenVPN и защита буфера"
        />
        <OpenVpnTuningCard activeNodeId={activeNodeId} nodeName={nodeName} disabled={disabled} />
        <OpenVpnBufferGuardCard activeNodeId={activeNodeId} nodeName={nodeName} disabled={disabled} />
      </section>
    </div>
  )
}
