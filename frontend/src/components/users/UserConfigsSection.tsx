import { useState } from 'react'
import { Download, KeyRound, QrCode, Trash2 } from 'lucide-react'
import {
  deleteUserConfig,
  downloadUserConfigFile,
  getUserConfigFiles,
  qrUserConfigFile,
  setUserConfigAccessOp,
} from '@/api/users'
import { ProvisioningConfigNode, UserProvisioningCard } from '@/types'
import { useNotifications } from '@/context/NotificationContext'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import EmptyState from '@/components/ui/EmptyState'
import UserSection from './UserSection'
import ConfirmDialog from '@/components/shared/ConfirmDialog'

interface ConfigEntry extends ProvisioningConfigNode {
  userId: number
  clientName: string
}

interface UserConfigsSectionProps {
  userId: number
  card: UserProvisioningCard
}

export default function UserConfigsSection({ userId, card }: UserConfigsSectionProps) {
  const { success, error: notifyError } = useNotifications()

  // Имена плана: индекс 1 → base, k → base-k (как plan_name_for_index на бэкенде).
  const base = (card.user.client_base_name ?? '').trim()
  const planNames = new Set(
    (card.user.plan_config_indexes ?? []).map((index) =>
      (index === 1 ? base : `${base}-${index}`).toLowerCase(),
    ),
  )
  const inPlan = (name: string) => planNames.has(name.toLowerCase())

  const [filesByEntry, setFilesByEntry] = useState<Record<string, string[]>>({})
  const [filesLoading, setFilesLoading] = useState<Set<string>>(new Set())
  const [deleteTarget, setDeleteTarget] = useState<ConfigEntry | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<Set<string>>(new Set())

  const configKey = (entry: ConfigEntry) => String(entry.config_id ?? entry.node_id)
  const isLoading = (key: string) => actionLoading.has(key)
  const entryFiles = (entry: ConfigEntry) => filesByEntry[configKey(entry)] ?? []
  const hasFiles = (entry: ConfigEntry) => Boolean(entryFiles(entry).length)

  const loadFiles = async (entry: ConfigEntry) => {
    if (!entry.config_id) return
    if (hasFiles(entry) || filesLoading.has(configKey(entry))) return
    setFilesLoading((prev) => new Set([...prev, configKey(entry)]))
    try {
      const data = await getUserConfigFiles(userId, entry.config_id)
      setFilesByEntry((prev) => ({ ...prev, [configKey(entry)]: data.files.map((f) => f.path) }))
    } catch {
      /* files unavailable on this node yet */
    } finally {
      setFilesLoading((prev) => {
        const next = new Set(prev)
        next.delete(configKey(entry))
        return next
      })
    }
  }

  const primaryPath = (entry: ConfigEntry) => entryFiles(entry)[0]

  const handleDownload = async (entry: ConfigEntry) => {
    if (!entry.config_id) return
    await loadFiles(entry)
    const path = primaryPath(entry)
    if (!path) return
    const key = `dl-${configKey(entry)}`
    setActionLoading((prev) => new Set([...prev, key]))
    try {
      const res = await downloadUserConfigFile(userId, entry.config_id, path)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = path.split('/').pop() ?? 'config'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      success('Конфиг скачан')
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка скачивания')
    } finally {
      setActionLoading((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }

  const handleQr = async (entry: ConfigEntry) => {
    if (!entry.config_id) return
    await loadFiles(entry)
    const path = primaryPath(entry)
    if (!path) return
    const key = `qr-${configKey(entry)}`
    setActionLoading((prev) => new Set([...prev, key]))
    try {
      const res = await qrUserConfigFile(userId, entry.config_id, path)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${entry.clientName}-qr.png`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка QR')
    } finally {
      setActionLoading((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }

  const handleAccessToggle = async (entry: ConfigEntry, op: 'block_temp' | 'block_perm' | 'unblock') => {
    if (!entry.config_id) return
    const key = `acc-${configKey(entry)}-${op}`
    setActionLoading((prev) => new Set([...prev, key]))
    try {
      await setUserConfigAccessOp(userId, entry.config_id, {
        op,
        days: op === 'block_temp' ? 7 : undefined,
      })
      success(`Доступ обновлён: ${op}`)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка изменения доступа')
    } finally {
      setActionLoading((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }

  const openDelete = (entry: ConfigEntry) => {
    setDeleteTarget(entry)
  }

  const runDelete = async () => {
    if (!deleteTarget || !deleteTarget.config_id) return
    setDeleteLoading(true)
    try {
      await deleteUserConfig(userId, deleteTarget.config_id)
      success('Конфиг удалён')
      setDeleteTarget(null)
      void loadFiles(deleteTarget) // refresh statuses
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка удаления')
    } finally {
      setDeleteLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <UserSection
        icon={KeyRound}
        title="Конфиги"
        description="По имени и узлу. Действия выполняются на узле конфига."
        actions={
          <Badge variant="secondary">
            {card.configs.length} имён ·{' '}
            {card.configs.reduce((total, group) => total + group.nodes.length, 0)} узлов
          </Badge>
        }
      >
        <div className="space-y-3">
          {!base && (
            <p className="rounded-lg border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
              Плана нет — показаны записи конфигов из базы панели. Конфиги, удалённые на узле
              напрямую, остаются здесь до синхронизации.
            </p>
          )}
          {card.configs.length === 0 ? (
            <EmptyState
              icon={KeyRound}
              title="Конфигов нет"
              description="Создайте их во вкладке «План» или дождитесь применения."
              className="py-10"
            />
          ) : (
            <div className="space-y-3">
              {card.configs.map((group) => (
                <div key={group.name} className="overflow-hidden rounded-xl border">
                  <div className="flex items-center justify-between gap-2 border-b bg-muted/50 px-3 py-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="truncate font-mono text-sm font-medium">{group.name}</span>
                      {base ? (
                        <Badge
                          variant={inPlan(group.name) ? 'success' : 'secondary'}
                          className="text-[10px]"
                        >
                          {inPlan(group.name) ? 'в плане' : 'вне плана'}
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-[10px]">
                          без плана
                        </Badge>
                      )}
                    </div>
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      узлов: {group.nodes.length}
                    </span>
                  </div>
                  <div className="p-3">
                    <div className="space-y-2">
                      {group.nodes.map((entry: ProvisioningConfigNode) => {
                        const configEntry: ConfigEntry = {
                          ...entry,
                          userId,
                          clientName: group.name,
                        }
                        const created = entry.config_id != null
                        const loadingKey = `cfg-${entry.config_id ?? entry.node_id}`
                        return (
                          <div
                            key={entry.config_id ?? entry.node_id}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5">
                                <span className="text-sm font-medium">{entry.node_label}</span>
                                <Badge variant="outline" className="text-[10px]">
                                  {entry.vpn_type}
                                </Badge>
                              </div>
                              <p className="mt-0.5 text-[11px] text-muted-foreground">
                                узел ID {entry.node_id}{entry.config_id ? ` · конфиг #${entry.config_id}` : ''}
                              </p>
                            </div>
                            <div className="flex items-center gap-1">
                              <Button
                                type="button"
                                size="sm"
                                disabled={!created || isLoading(loadingKey)}
                                onClick={() => void handleDownload(configEntry)}
                              >
                                <Download size={13} />
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                disabled={!created || isLoading(loadingKey)}
                                onClick={() => void handleQr(configEntry)}
                              >
                                <QrCode size={13} />
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                disabled={!created}
                                onClick={() => void handleAccessToggle(configEntry, 'unblock')}
                              >
                                Доступ
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="destructive"
                                disabled={!created || isLoading(loadingKey)}
                                onClick={() => void openDelete(configEntry)}
                              >
                                <Trash2 size={13} />
                              </Button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </UserSection>

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open: boolean) => {
          if (!open && !deleteLoading) setDeleteTarget(null)
        }}
        title="Удалить конфиг?"
        description={
          deleteTarget ? (
            <>
              Конфиг «{deleteTarget.clientName}» на узле {deleteTarget.node_label} будет удалён без возможности восстановления.
            </>
          ) : null}
        confirmLabel="Удалить"
        destructive
        loading={deleteLoading}
        onConfirm={runDelete}
      />
    </div>
  )
}
