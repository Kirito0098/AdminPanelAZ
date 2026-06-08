import { useEffect, useState } from 'react'
import { Archive, ArchiveX, Download, Trash2 } from 'lucide-react'
import {
  ApiError,
  createBackup,
  deleteBackup,
  downloadBackup,
  getBackupSettings,
  getBackups,
  restoreBackup,
  updateBackupSettings,
} from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import type { BackupEntry, BackupSettings } from '@/types'

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function BackupTab() {
  const { success, error: notifyError } = useNotifications()
  const { inline, withInline } = useProgress()
  const { confirm, dialogProps } = useConfirmDialog()
  const [backups, setBackups] = useState<BackupEntry[]>([])
  const [settings, setSettings] = useState<BackupSettings | null>(null)
  const [includeConfigs, setIncludeConfigs] = useState(false)
  const [includeAntizapretBackup, setIncludeAntizapretBackup] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    const [list, cfg] = await Promise.all([getBackups(), getBackupSettings()])
    setBackups(list)
    setSettings(cfg)
  }

  useEffect(() => {
    setLoading(true)
    load()
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки бэкапов'))
      .finally(() => setLoading(false))
  }, [])

  const handleCreate = async () => {
    try {
      await withInline(async () => {
        await createBackup(includeConfigs, includeAntizapretBackup)
        await load()
      }, 'Создание бэкапа...')
      success('Бэкап создан')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания бэкапа')
    }
  }

  const handleRestore = (fileName: string) => {
    confirm({
      title: 'Восстановить из бэкапа?',
      description: <>Архив «{fileName}» будет развёрнут на сервере панели.</>,
      alert: {
        variant: 'danger',
        title: 'Перезапуск панели',
        children: 'После восстановления необходимо перезапустить панель вручную. Текущие данные будут перезаписаны.',
      },
      confirmLabel: 'Восстановить',
      destructive: true,
      onConfirm: async () => {
        try {
          await withInline(async () => {
            await restoreBackup(fileName)
            await load()
          }, 'Восстановление...')
          success('Восстановление выполнено — перезапустите панель')
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка восстановления')
        }
      },
    })
  }

  const handleDelete = (fileName: string) => {
    confirm({
      title: 'Удалить архив?',
      description: <>Архив «{fileName}» будет удалён без возможности восстановления.</>,
      confirmLabel: 'Удалить',
      destructive: true,
      onConfirm: async () => {
        try {
          await deleteBackup(fileName)
          await load()
          success('Архив удалён')
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления')
        }
      },
    })
  }

  const toggleTelegramBackup = async () => {
    if (!settings) return
    try {
      const updated = await updateBackupSettings({ telegram_on_backup: !settings.telegram_on_backup })
      setSettings(updated)
      success('Настройки бэкапа обновлены')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    }
  }

  if (loading) {
    return <Spinner label="Загрузка бэкапов..." className="py-12" />
  }

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <InlineProgressBar active={inline.active} label={inline.label} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Archive size={18} />
            Создание бэкапа
          </CardTitle>
          <CardDescription>
            Бэкап БД панели, .env, списков AntiZapret и опционально полного архива VPN (client.sh 8) на активном узле
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-center">
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeConfigs}
                onChange={(e) => setIncludeConfigs(e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              Включить списки AntiZapret
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeAntizapretBackup}
                onChange={(e) => setIncludeAntizapretBackup(e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              Бэкап AntiZapret (client.sh 8)
            </label>
            {settings && (
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.telegram_on_backup}
                  onChange={toggleTelegramBackup}
                  className="h-4 w-4 rounded border"
                />
                Отправлять в Telegram
              </label>
            )}
            <Button onClick={handleCreate} className="sm:ml-auto">
              Создать бэкап
            </Button>
          </div>
        </CardContent>
      </Card>

      {settings && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Автоматизация</CardTitle>
            <CardDescription>Периодическое создание и ротация архивов</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 rounded-md border p-4 md:grid-cols-3">
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.auto_backup_enabled}
                  onChange={async () => {
                    const updated = await updateBackupSettings({ auto_backup_enabled: !settings.auto_backup_enabled })
                    setSettings(updated)
                  }}
                  className="h-4 w-4 rounded border"
                />
                Авто-бэкап
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.backup_az_enabled}
                  onChange={async () => {
                    const updated = await updateBackupSettings({ backup_az_enabled: !settings.backup_az_enabled })
                    setSettings(updated)
                  }}
                  className="h-4 w-4 rounded border"
                />
                AntiZapret (client.sh 8) при авто-бэкапе
              </label>
              <div className="space-y-2">
                <Label htmlFor="backup-days">Интервал (дней)</Label>
                <Input
                  id="backup-days"
                  type="number"
                  min={1}
                  max={90}
                  value={settings.auto_backup_days}
                  onChange={async (e) => {
                    const updated = await updateBackupSettings({ auto_backup_days: Number(e.target.value) })
                    setSettings(updated)
                  }}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="retention">Хранить архивов</Label>
                <Input
                  id="retention"
                  type="number"
                  min={1}
                  max={30}
                  value={settings.retention_count}
                  onChange={async (e) => {
                    const updated = await updateBackupSettings({ retention_count: Number(e.target.value) })
                    setSettings(updated)
                  }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Архивы</CardTitle>
          <CardDescription>
            {backups.length > 0 ? `${backups.length} архив${backups.length === 1 ? '' : backups.length < 5 ? 'а' : 'ов'}` : 'Список сохранённых копий'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {backups.length === 0 ? (
            <EmptyState
              icon={ArchiveX}
              title="Архивов пока нет"
              description="Создайте первый бэкап, чтобы защитить данные панели"
              action={
                <Button onClick={handleCreate} variant="secondary">
                  Создать бэкап
                </Button>
              }
              className="py-8"
            />
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Файл</TableHead>
                    <TableHead>Размер</TableHead>
                    <TableHead>Дата</TableHead>
                    <TableHead>Состав</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {backups.map((b) => (
                    <TableRow key={b.file_name}>
                      <TableCell className="font-mono text-xs">{b.file_name}</TableCell>
                      <TableCell>{formatSize(b.size_bytes)}</TableCell>
                      <TableCell>{new Date(b.created_at).toLocaleString('ru-RU')}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {b.components.map((c) => (
                            <Badge key={c} variant="secondary">
                              {c}
                            </Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="space-x-1 text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          title="Скачать"
                          onClick={async () => {
                            const res = await downloadBackup(b.file_name)
                            if (!res.ok) return notifyError('Ошибка скачивания')
                            const blob = await res.blob()
                            const a = document.createElement('a')
                            a.href = URL.createObjectURL(blob)
                            a.download = b.file_name
                            a.click()
                          }}
                        >
                          <Download size={14} />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="border-destructive/30 text-destructive hover:bg-destructive/10"
                          onClick={() => handleRestore(b.file_name)}
                        >
                          Восстановить
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="border-destructive/30 text-destructive hover:bg-destructive/10"
                          onClick={() => handleDelete(b.file_name)}
                        >
                          <Trash2 size={14} />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <SettingsAlert variant="danger" title="Восстановление из бэкапа">
        Восстановление перезапишет текущие данные панели. После операции необходимо перезапустить панель вручную.
      </SettingsAlert>
    </div>
  )
}
