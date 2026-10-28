import { useState } from 'react'
import { Copy, Download, FileKey, KeyRound, Loader2, QrCode, Trash2 } from 'lucide-react'
import {
  deleteUserConfig,
  downloadUserConfigFile,
  fetchUserConfigQrBlob,
  getUserConfigFiles,
  setUserConfigAccessOp,
  type UserConfigFile,
  type UserQrContentMode,
} from '@/api/users'
import { ProvisioningConfigNode, UserProvisioningCard } from '@/types'
import { useNotifications } from '@/context/NotificationContext'
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
import EmptyState from '@/components/ui/EmptyState'
import { parseContentDispositionFilename } from '@/lib/profileDownloadName'
import { triggerFileDownload } from '@/lib/triggerFileDownload'
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

type FilePickMode = 'download' | 'qr'

type FilePickState = {
  entry: ConfigEntry
  mode: FilePickMode
  files: UserConfigFile[]
}

type QrPreviewState = {
  url: string
  filename: string
  contentMode: UserQrContentMode
  downloadUrl?: string
}

function fileLabel(file: UserConfigFile): string {
  const variant = (file.variant || '').trim()
  if (!variant) return file.protocol || 'Профиль'
  if (variant === 'vpn' || variant === 'antizapret') {
    return variant === 'vpn' ? 'VPN профиль' : 'AntiZapret'
  }
  if (variant.startsWith('vpn')) return `VPN (${variant.replace(/^vpn-?/, '') || 'профиль'})`
  if (variant.startsWith('antizapret')) {
    return `AntiZapret (${variant.replace(/^antizapret-?/, '') || 'профиль'})`
  }
  return variant
}

function fileDisplayName(file: UserConfigFile): string {
  return file.download_filename || file.filename || file.path.split('/').pop() || 'config'
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

  const [filesByEntry, setFilesByEntry] = useState<Record<string, UserConfigFile[]>>({})
  const [filesLoading, setFilesLoading] = useState<Set<string>>(new Set())
  const [deleteTarget, setDeleteTarget] = useState<ConfigEntry | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<Set<string>>(new Set())
  const [filePick, setFilePick] = useState<FilePickState | null>(null)
  const [qrPreview, setQrPreview] = useState<QrPreviewState | null>(null)

  const configKey = (entry: ConfigEntry) => String(entry.config_id ?? entry.node_id)
  const isLoading = (key: string) => actionLoading.has(key) || filesLoading.has(key)

  const loadFiles = async (entry: ConfigEntry): Promise<UserConfigFile[]> => {
    if (!entry.config_id) return []
    const key = configKey(entry)
    const cached = filesByEntry[key]
    if (cached?.length) return cached
    if (filesLoading.has(key)) return []
    setFilesLoading((prev) => new Set([...prev, key]))
    try {
      const data = await getUserConfigFiles(userId, entry.config_id)
      const files = data.files
      setFilesByEntry((prev) => ({ ...prev, [key]: files }))
      return files
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось получить файлы профиля')
      return []
    } finally {
      setFilesLoading((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }

  const runDownload = async (entry: ConfigEntry, file: UserConfigFile) => {
    if (!entry.config_id) return
    const key = `dl-${configKey(entry)}`
    setActionLoading((prev) => new Set([...prev, key]))
    try {
      const res = await downloadUserConfigFile(userId, entry.config_id, file.path)
      const blob = await res.blob()
      const downloadName =
        parseContentDispositionFilename(res.headers.get('Content-Disposition')) ??
        fileDisplayName(file)
      triggerFileDownload(blob, downloadName)
      success(`Файл «${downloadName}» скачан`)
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

  const runQr = async (entry: ConfigEntry, file: UserConfigFile) => {
    if (!entry.config_id) return
    const key = `qr-${configKey(entry)}`
    setActionLoading((prev) => new Set([...prev, key]))
    try {
      const { blob, contentMode, downloadUrl } = await fetchUserConfigQrBlob(
        userId,
        entry.config_id,
        file.path,
      )
      const url = URL.createObjectURL(blob)
      setQrPreview({
        url,
        filename: fileDisplayName(file),
        contentMode,
        downloadUrl,
      })
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

  const openFileAction = async (entry: ConfigEntry, mode: FilePickMode) => {
    if (!entry.config_id) return
    const files = await loadFiles(entry)
    if (!files.length) {
      notifyError('Нет файлов профиля на узле')
      return
    }
    if (files.length === 1) {
      if (mode === 'download') {
        await runDownload(entry, files[0])
      } else {
        await runQr(entry, files[0])
      }
      return
    }
    setFilePick({ entry, mode, files })
  }

  const pickFile = async (file: UserConfigFile) => {
    if (!filePick) return
    const { entry, mode } = filePick
    setFilePick(null)
    if (mode === 'download') {
      await runDownload(entry, file)
    } else {
      await runQr(entry, file)
    }
  }

  const copyQrDownloadUrl = async () => {
    if (!qrPreview?.downloadUrl) return
    try {
      await navigator.clipboard.writeText(qrPreview.downloadUrl)
      success('Ссылка скопирована в буфер')
    } catch {
      notifyError('Не удалось скопировать ссылку')
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
      setFilesByEntry((prev) => {
        const next = { ...prev }
        delete next[configKey(deleteTarget)]
        return next
      })
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
                        const loadingKey = configKey(configEntry)
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
                                узел ID {entry.node_id}
                                {entry.config_id ? ` · конфиг #${entry.config_id}` : ''}
                              </p>
                            </div>
                            <div className="flex items-center gap-1">
                              <Button
                                type="button"
                                size="sm"
                                title="Скачать"
                                disabled={!created || isLoading(loadingKey)}
                                onClick={() => void openFileAction(configEntry, 'download')}
                              >
                                {filesLoading.has(loadingKey) ? (
                                  <Loader2 size={13} className="animate-spin" />
                                ) : (
                                  <Download size={13} />
                                )}
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                title="QR-код"
                                disabled={!created || isLoading(loadingKey)}
                                onClick={() => void openFileAction(configEntry, 'qr')}
                              >
                                {actionLoading.has(`qr-${loadingKey}`) ||
                                filesLoading.has(loadingKey) ? (
                                  <Loader2 size={13} className="animate-spin" />
                                ) : (
                                  <QrCode size={13} />
                                )}
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

      <Dialog
        open={filePick != null}
        onOpenChange={(open) => {
          if (!open) setFilePick(null)
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {filePick?.mode === 'qr' ? 'QR-код профиля' : 'Скачать профиль'}
            </DialogTitle>
            <DialogDescription>
              {filePick
                ? `${filePick.entry.clientName} · ${filePick.entry.node_label}`
                : null}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {filePick?.files.map((file) => (
              <div
                key={file.path}
                className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{fileLabel(file)}</p>
                  <p className="truncate text-[11px] text-muted-foreground">
                    {fileDisplayName(file)}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void pickFile(file)}
                >
                  {filePick.mode === 'qr' ? <QrCode size={14} /> : <Download size={14} />}
                  {filePick.mode === 'qr' ? 'QR' : 'Скачать'}
                </Button>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={qrPreview != null}
        onOpenChange={(open) => {
          if (!open && qrPreview) {
            URL.revokeObjectURL(qrPreview.url)
            setQrPreview(null)
          }
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileKey size={18} />
              {qrPreview?.contentMode === 'download-link'
                ? 'QR: ссылка для скачивания'
                : 'QR-код профиля'}
            </DialogTitle>
            <DialogDescription>
              {qrPreview?.filename}
              {qrPreview?.contentMode === 'download-link' ? (
                <span className="mt-1 block text-xs text-muted-foreground">
                  Профиль не помещается в один QR (типично для AntiZapret WG/AWG и OpenVPN).
                  Отсканируйте камерой телефона — откроется ссылка для скачивания файла, не импорт
                  в VPN-приложение.
                </span>
              ) : (
                <span className="mt-1 block text-xs text-muted-foreground">
                  Отсканируйте VPN-приложением для импорта профиля.
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          {qrPreview && (
            <div className="flex justify-center rounded-lg border bg-muted/30 p-6">
              <img src={qrPreview.url} alt="QR-код конфигурации" className="max-h-72 rounded-md" />
            </div>
          )}
          {qrPreview?.downloadUrl && (
            <DialogFooter className="sm:justify-center">
              <Button type="button" variant="outline" onClick={() => void copyQrDownloadUrl()}>
                <Copy size={14} />
                Скопировать ссылку
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open: boolean) => {
          if (!open && !deleteLoading) setDeleteTarget(null)
        }}
        title="Удалить конфиг?"
        description={
          deleteTarget ? (
            <>
              Конфиг «{deleteTarget.clientName}» на узле {deleteTarget.node_label} будет удалён без
              возможности восстановления.
            </>
          ) : null
        }
        confirmLabel="Удалить"
        destructive
        loading={deleteLoading}
        onConfirm={runDelete}
      />
    </div>
  )
}
