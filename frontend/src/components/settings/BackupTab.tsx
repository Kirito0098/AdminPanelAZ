import { useEffect, useState } from 'react'
import { Archive, Download, Trash2 } from 'lucide-react'
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
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
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
  const [backups, setBackups] = useState<BackupEntry[]>([])
  const [settings, setSettings] = useState<BackupSettings | null>(null)
  const [includeConfigs, setIncludeConfigs] = useState(false)

  const load = async () => {
    const [list, cfg] = await Promise.all([getBackups(), getBackupSettings()])
    setBackups(list)
    setSettings(cfg)
  }

  useEffect(() => {
    load().catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки бэкапов'))
  }, [])

  const handleCreate = async () => {
    try {
      await withInline(async () => {
        await createBackup(includeConfigs)
        await load()
      }, 'Создание бэкапа...')
      success('Бэкап создан')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания бэкапа')
    }
  }

  const handleRestore = async (fileName: string) => {
    if (!confirm(`Восстановить из «${fileName}»? Панель нужно будет перезапустить.`)) return
    try {
      await withInline(() => restoreBackup(fileName), 'Восстановление...')
      success('Восстановление выполнено — перезапустите панель')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка восстановления')
    }
  }

  const handleDelete = async (fileName: string) => {
    if (!confirm(`Удалить «${fileName}»?`)) return
    try {
      await deleteBackup(fileName)
      await load()
      success('Архив удалён')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления')
    }
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

  return (
    <div className="space-y-4">
      <InlineProgressBar active={inline.active} label={inline.label} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Archive size={18} />
            Резервное копирование
          </CardTitle>
          <CardDescription>Бэкап БД панели, .env и опционально списков AntiZapret с активного узла</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeConfigs}
                onChange={(e) => setIncludeConfigs(e.target.checked)}
                className="rounded border"
              />
              Включить списки AntiZapret
            </label>
            {settings && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.telegram_on_backup}
                  onChange={toggleTelegramBackup}
                  className="rounded border"
                />
                Отправлять в Telegram
              </label>
            )}
            <Button onClick={handleCreate}>Создать бэкап</Button>
          </div>
          {settings && (
            <div className="grid gap-4 rounded-md border p-4 md:grid-cols-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.auto_backup_enabled}
                  onChange={async () => {
                    const updated = await updateBackupSettings({ auto_backup_enabled: !settings.auto_backup_enabled })
                    setSettings(updated)
                  }}
                />
                Авто-бэкап
              </label>
              <label className="flex items-center gap-2 text-sm">
                Интервал (дней):
                <input
                  type="number"
                  min={1}
                  max={90}
                  className="w-16 rounded border px-2 py-1"
                  value={settings.auto_backup_days}
                  onChange={async (e) => {
                    const updated = await updateBackupSettings({ auto_backup_days: Number(e.target.value) })
                    setSettings(updated)
                  }}
                />
              </label>
              <label className="flex items-center gap-2 text-sm">
                Хранить:
                <input
                  type="number"
                  min={1}
                  max={30}
                  className="w-16 rounded border px-2 py-1"
                  value={settings.retention_count}
                  onChange={async (e) => {
                    const updated = await updateBackupSettings({ retention_count: Number(e.target.value) })
                    setSettings(updated)
                  }}
                />
                архивов
              </label>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Архивы</CardTitle>
        </CardHeader>
        <CardContent>
          {backups.length === 0 ? (
            <p className="text-sm text-muted-foreground">Архивов пока нет</p>
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
                        <Button variant="outline" size="sm" onClick={() => handleRestore(b.file_name)}>
                          Восстановить
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="border-destructive/30 text-destructive"
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
    </div>
  )
}
