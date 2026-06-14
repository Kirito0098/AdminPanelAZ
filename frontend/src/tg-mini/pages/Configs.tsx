import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import Spinner from '@/components/ui/Spinner'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import { getTgConfigFiles, getTgConfigs, getTgQrLink, sendTgConfig } from '@/tg-mini/api'
import type { TgMiniConfig, TgMiniConfigFile } from '@/types'

export default function Configs() {
  const { isAdmin } = useTgAuth()
  const [configs, setConfigs] = useState<TgMiniConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeConfig, setActiveConfig] = useState<TgMiniConfig | null>(null)
  const [files, setFiles] = useState<TgMiniConfigFile[]>([])
  const [selectedPath, setSelectedPath] = useState('')
  const [sheetLoading, setSheetLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getTgConfigs()
      setConfigs(data.configs)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const openActions = async (config: TgMiniConfig) => {
    setActiveConfig(config)
    setMessage(null)
    setSheetLoading(true)
    try {
      const data = await getTgConfigFiles(config.id)
      setFiles(data.files)
      setSelectedPath(data.files[0]?.path || '')
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Ошибка загрузки файлов')
      setFiles([])
    } finally {
      setSheetLoading(false)
    }
  }

  const closeSheet = () => {
    setActiveConfig(null)
    setFiles([])
    setSelectedPath('')
    setMessage(null)
  }

  const handleSend = async (destination: 'self' | 'chat') => {
    if (!activeConfig || !selectedPath) return
    setActionLoading(true)
    setMessage(null)
    try {
      const result = await sendTgConfig(activeConfig.id, { path: selectedPath, destination })
      setMessage(result.message)
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Ошибка отправки')
    } finally {
      setActionLoading(false)
    }
  }

  const handleQrLink = async () => {
    if (!activeConfig || !selectedPath) return
    setActionLoading(true)
    setMessage(null)
    try {
      const link = await getTgQrLink(activeConfig.id, selectedPath)
      await navigator.clipboard.writeText(link.url)
      setMessage('Ссылка скопирована в буфер обмена')
      window.Telegram?.WebApp.openLink(link.url)
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Ошибка создания ссылки')
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="tg-mini-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-destructive">{error}</p>}
      {configs.length === 0 ? (
        <p className="tg-mini-muted">Нет конфигов</p>
      ) : (
        configs.map((config) => (
          <Card key={config.id}>
            <CardContent className="p-4 flex items-center justify-between gap-3">
              <div>
                <div className="font-medium">{config.client_name}</div>
                <div className="text-sm text-muted-foreground">{config.vpn_type}</div>
              </div>
              <Button type="button" size="sm" onClick={() => void openActions(config)}>
                Действия
              </Button>
            </CardContent>
          </Card>
        ))
      )}

      <Dialog open={Boolean(activeConfig)} onOpenChange={(open) => !open && closeSheet()}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{activeConfig?.client_name}</DialogTitle>
            <DialogDescription>Отправка конфига или одноразовая ссылка</DialogDescription>
          </DialogHeader>

          {sheetLoading ? (
            <div className="tg-mini-center py-6">
              <Spinner />
            </div>
          ) : (
            <div className="space-y-3">
              {files.length > 1 && (
                <select
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  value={selectedPath}
                  onChange={(e) => setSelectedPath(e.target.value)}
                >
                  {files.map((file) => (
                    <option key={file.path} value={file.path}>
                      {file.download_filename || file.filename || file.path}
                    </option>
                  ))}
                </select>
              )}
              {files.length === 1 && (
                <p className="text-sm text-muted-foreground">
                  {files[0].download_filename || files[0].filename || files[0].path}
                </p>
              )}
              {message && <p className="text-sm">{message}</p>}
            </div>
          )}

          <DialogFooter className="flex-col gap-2 sm:flex-col">
            <Button
              type="button"
              disabled={actionLoading || sheetLoading || !selectedPath}
              onClick={() => void handleSend('self')}
            >
              Отправить себе
            </Button>
            {isAdmin && (
              <Button
                type="button"
                variant="outline"
                disabled={actionLoading || sheetLoading || !selectedPath}
                onClick={() => void handleSend('chat')}
              >
                Отправить в общий chat
              </Button>
            )}
            <Button
              type="button"
              variant="secondary"
              disabled={actionLoading || sheetLoading || !selectedPath}
              onClick={() => void handleQrLink()}
            >
              QR-ссылка
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
