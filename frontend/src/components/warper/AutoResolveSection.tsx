import { useCallback, useEffect, useState } from 'react'
import { Eraser, Globe, ListTree, RefreshCw } from 'lucide-react'
import {
  getWarperAutoResolve,
  getWarperIpRoutes,
  postWarperClearIpRoutes,
  postWarperResolveClean,
  postWarperResolveSync,
  setWarperAutoResolve,
} from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { WarperHealthResponse } from '@/types'
import WarperSection from './WarperSection'
import { isWarperDisabled } from './utils'

interface AutoResolveSectionProps {
  health: WarperHealthResponse | null
  onRangesChanged: () => void
}

export default function AutoResolveSection({ health, onRangesChanged }: AutoResolveSectionProps) {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const disabled = isWarperDisabled(health)

  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [unsupported, setUnsupported] = useState<string | null>(null)
  const [routes, setRoutes] = useState<string[] | null>(null)
  const [cleanDomain, setCleanDomain] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!health?.installed) return
    try {
      const data = await getWarperAutoResolve()
      setEnabled(data.enabled)
      setUnsupported(null)
    } catch (err) {
      setEnabled(null)
      setUnsupported(err instanceof Error ? err.message : 'Авто-резолв недоступен')
    }
  }, [health?.installed])

  useEffect(() => {
    setRoutes(null)
    void load()
  }, [load, activeNode?.id])

  async function run(action: () => Promise<{ message?: string | null }>, okMessage: string, refreshRanges = false) {
    setBusy(true)
    try {
      const result = await action()
      success(result.message || okMessage)
      await load()
      if (refreshRanges) onRangesChanged()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Ошибка AZ-WARP')
    } finally {
      setBusy(false)
    }
  }

  async function loadRoutes() {
    setBusy(true)
    try {
      setRoutes((await getWarperIpRoutes()).routes)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось получить маршруты')
    } finally {
      setBusy(false)
    }
  }

  function handleClean() {
    const domain = cleanDomain.trim()
    confirm({
      title: domain ? `Очистить адреса домена ${domain}?` : 'Очистить весь блок RESOLVED?',
      description:
        'Адреса удаляются из ip-ranges.txt, маршруты синхронизируются. Установленные соединения к этим IP могут оборваться.',
      confirmLabel: 'Очистить',
      destructive: true,
      onConfirm: () => run(() => postWarperResolveClean(domain || null), 'Блок RESOLVED очищен', true),
    })
  }

  function handleClearRoutes() {
    confirm({
      title: 'Снять все IP-маршруты AZ-WARP?',
      description:
        'Маршруты удаляются из ядра, файл ip-ranges.txt не меняется. Вернуть их можно синхронизацией подсетей или resync.',
      confirmLabel: 'Снять маршруты',
      destructive: true,
      onConfirm: async () => {
        await run(() => postWarperClearIpRoutes(), 'IP-маршруты сняты')
        setRoutes(null)
      },
    })
  }

  const controlsDisabled = disabled || busy || enabled === null

  return (
    <>
      <ConfirmDialogHost dialogProps={dialogProps} />
      <WarperSection
        title="Авто-резолв доменов в IP-маршруты"
        icon={Globe}
        description="Раз в час домены из списка резолвятся, адреса накапливаются в блоке RESOLVED файла ip-ranges.txt"
      >
        {unsupported ? (
          <p className="text-sm text-muted-foreground">
            Недоступно на этом узле: {unsupported}
          </p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
              <div>
                <div className="text-sm font-medium">Авто-резолв</div>
                <p className="text-xs text-muted-foreground">
                  Помогает, когда приложение ходит по IP в обход DNS. Список накопительный: старые адреса не
                  удаляются, чтобы не рвать соединения.
                </p>
              </div>
              <Switch
                checked={Boolean(enabled)}
                disabled={controlsDisabled}
                onCheckedChange={(checked) =>
                  void run(() => setWarperAutoResolve(checked), checked ? 'Авто-резолв включён' : 'Авто-резолв выключен')
                }
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={controlsDisabled}
                onClick={() => void run(() => postWarperResolveSync(false), 'Резолв выполнен', true)}
              >
                <RefreshCw className="mr-1.5 h-4 w-4" />
                Резолвить сейчас
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={controlsDisabled}
                onClick={() => void run(() => postWarperResolveSync(true), 'Резолв и синхронизация выполнены', true)}
              >
                С принудительной синхронизацией
              </Button>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                placeholder="домен (пусто — весь блок)"
                value={cleanDomain}
                disabled={controlsDisabled}
                onChange={(e) => setCleanDomain(e.target.value)}
              />
              <Button size="sm" variant="outline" disabled={controlsDisabled} onClick={handleClean}>
                <Eraser className="mr-1.5 h-4 w-4" />
                Очистить RESOLVED
              </Button>
            </div>
          </div>
        )}
      </WarperSection>

      <WarperSection
        title="Применённые маршруты"
        icon={ListTree}
        description="CIDR, которые сейчас стоят в ядре через singbox-tun"
      >
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" disabled={disabled || busy} onClick={() => void loadRoutes()}>
              Показать маршруты
            </Button>
            <Button size="sm" variant="outline" disabled={disabled || busy} onClick={handleClearRoutes}>
              Снять все маршруты
            </Button>
            {routes && <Badge variant="secondary">Маршрутов: {routes.length}</Badge>}
          </div>
          {routes && routes.length > 0 && (
            <pre className="max-h-56 overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-xs leading-relaxed">
              {routes.join('\n')}
            </pre>
          )}
        </div>
      </WarperSection>
    </>
  )
}
