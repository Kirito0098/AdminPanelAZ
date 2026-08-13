import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, TerminalSquare } from 'lucide-react'
import { openAwg2InstallStream } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button, type ButtonProps } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useNotifications } from '@/context/NotificationContext'
import { AWG2_PRESETS, AWG2_TEMPLATES } from './utils'

interface Awg2InstallDialogProps {
  mode: 'install' | 'update'
  triggerLabel: string
  triggerVariant?: ButtonProps['variant']
  triggerSize?: ButtonProps['size']
  disabled?: boolean
  onCompleted?: () => void
}

export default function Awg2InstallDialog({
  mode,
  triggerLabel,
  triggerVariant = 'default',
  triggerSize = 'sm',
  disabled = false,
  onCompleted,
}: Awg2InstallDialogProps) {
  const { success, error: notifyError } = useNotifications()
  const streamRef = useRef<EventSource | null>(null)
  const [open, setOpen] = useState(false)
  const [running, setRunning] = useState(false)
  const [preset, setPreset] = useState<string>('medium')
  const [template, setTemplate] = useState<string>('web')
  const [logLines, setLogLines] = useState<string[]>([])
  const [lastError, setLastError] = useState<string | null>(null)
  const [finished, setFinished] = useState<{ success: boolean; returnCode?: number | null } | null>(null)

  const closeStream = useCallback(() => {
    streamRef.current?.close()
    streamRef.current = null
  }, [])

  useEffect(() => () => closeStream(), [closeStream])

  const handleOpenChange = (nextOpen: boolean) => {
    if (running) return
    setOpen(nextOpen)
    if (!nextOpen) {
      setLastError(null)
      setFinished(null)
      setLogLines([])
    }
  }

  const handleStart = () => {
    closeStream()
    setLastError(null)
    setFinished(null)
    setLogLines([])
    setRunning(true)

    const source = openAwg2InstallStream(
      mode === 'install'
        ? {
            mode,
            preset,
            template,
          }
        : { mode },
      (event) => {
        if (event.event === 'start') {
          const argv = event.argv
          if (argv?.length) {
            setLogLines((prev) => [...prev, `$ ${argv.join(' ')}`])
          }
          return
        }
        if (event.event === 'log') {
          const line = event.line
          if (line) {
            setLogLines((prev) => [...prev, line])
          }
          return
        }
        if (event.event === 'done') {
          closeStream()
          setRunning(false)
          setFinished({ success: event.success, returnCode: event.return_code })
          if (event.success) {
            success(mode === 'install' ? 'AZ-AWG2 успешно установлен' : 'AZ-AWG2 успешно обновлён')
            onCompleted?.()
          } else {
            notifyError(`Операция завершилась с кодом ${event.return_code ?? '—'}`)
          }
          return
        }
        if (event.event === 'error') {
          closeStream()
          setRunning(false)
          setLastError(event.detail || 'Ошибка потока AZ-AWG2')
          notifyError(event.detail || 'Ошибка потока AZ-AWG2')
        }
      },
      (message) => {
        closeStream()
        setRunning(false)
        setLastError(message)
        notifyError(message)
      },
    )

    if (!source) {
      setRunning(false)
      setLastError('Не удалось открыть поток установки AZ-AWG2')
      notifyError('Не удалось открыть поток установки AZ-AWG2')
      return
    }

    streamRef.current = source
  }

  return (
    <>
      <Button variant={triggerVariant} size={triggerSize} disabled={disabled} onClick={() => setOpen(true)}>
        {running ? <Loader2 className="animate-spin" /> : <TerminalSquare className="h-4 w-4" />}
        {triggerLabel}
      </Button>

      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{mode === 'install' ? 'Установить AZ-AWG2 из панели' : 'Обновить слой AZ-AWG2'}</DialogTitle>
            <DialogDescription>
              {mode === 'install'
                ? 'Панель запускает upstream install.sh на активном узле и показывает live-лог выполнения.'
                : 'Панель запускает обновление слоя на активном узле и показывает live-лог выполнения.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <SettingsAlert variant="warning" title="Только через SSH">
              Перезагрузка узла и базовая установка AntiZapret (`install-base`) остаются только в SSH.
              Панель не показывает и не запускает `--install-base`.
            </SettingsAlert>

            {mode === 'install' && (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="awg2-install-preset">Preset</Label>
                  <Select value={preset} onValueChange={setPreset} disabled={running}>
                    <SelectTrigger id="awg2-install-preset">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {AWG2_PRESETS.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="awg2-install-template">Template</Label>
                  <Select value={template} onValueChange={setTemplate} disabled={running}>
                    <SelectTrigger id="awg2-install-template">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {AWG2_TEMPLATES.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {lastError && (
              <SettingsAlert variant="danger" title="Ошибка">
                {lastError}
              </SettingsAlert>
            )}

            {finished?.success && (
              <SettingsAlert variant="info" title="Готово">
                {mode === 'install' ? 'Установка завершена успешно.' : 'Обновление завершено успешно.'}
              </SettingsAlert>
            )}

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium">Лог выполнения</p>
                {finished && !finished.success && (
                  <span className="text-xs text-destructive">Код завершения: {finished.returnCode ?? '—'}</span>
                )}
              </div>
              <pre className="min-h-48 max-h-80 overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs leading-relaxed">
                {logLines.length > 0
                  ? logLines.join('\n')
                  : running
                    ? 'Открываем поток...'
                    : 'Лог появится после запуска операции.'}
              </pre>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" disabled={running} onClick={() => setOpen(false)}>
              Закрыть
            </Button>
            <Button type="button" disabled={running} onClick={handleStart}>
              {running ? (
                <>
                  <Loader2 className="animate-spin" />
                  Выполняется...
                </>
              ) : (
                triggerLabel
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
