import {
  ApiError,
  getBufferGuardEvents,
  getBufferGuardSettings,
  putBufferGuardSettings,
  scanBufferGuard,
} from '@/api/client'
import type { OpenVpnBufferGuardScanResult } from '@/api/openvpnBufferGuard'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { formatDateTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { OpenVpnBufferGuardMode, OpenVpnBufferGuardSettings, OpenVpnBufferGuardEvent } from '@/types'
import { AlertTriangle, CheckCircle2, ShieldAlert, Timer, Zap } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

const MODE_LABELS: Record<OpenVpnBufferGuardMode, string> = {
  notify: 'Только уведомлять (без действий)',
  kill: 'Отключать клиента',
  kill_restart: 'Отключать + перезапускать OpenVPN',
  kill_restart_temp_ban: 'Отключать, перезапускать и временно банить',
}

const MODE_HINTS: Record<OpenVpnBufferGuardMode, string> = {
  notify:
    'Фиксирует ENOBUFS в логах и шлёт уведомления администраторам. Клиенты не трогаются автоматически.',
  kill:
    'При превышении порога отключает самого «шумного» клиента через management-сокет / API. Сервер не перезапускается.',
  kill_restart:
    'После отключения проверяет лог ещё раз: если ENOBUFS продолжаются, перезапускает OpenVPN для выбранных юнитов.',
  kill_restart_temp_ban:
    'Как kill_restart, но дополнительно заносит клиента во временный бан списком banned_clients (через AccessPolicy).',
}

const WATCH_UNIT_LABELS: Record<string, string> = {
  'antizapret-udp': 'antizapret-udp (legacy UDP)',
  'antizapret-tcp': 'antizapret-tcp (legacy TCP)',
  'vpn-udp': 'vpn-udp (основной UDP-сервер)',
  'vpn-tcp': 'vpn-tcp (основной TCP-сервер)',
}

const DEFAULT_WATCH_UNITS: string[] = ['antizapret-udp', 'vpn-udp']

export type OpenVpnBufferGuardCardProps = {
  activeNodeId: number | null
  nodeName?: string | null
  disabled?: boolean
}

function sortUnits(units: string[]): string[] {
  return [...units].sort()
}

function normalizeSettingsForNode(
  nodeId: number,
  settings: OpenVpnBufferGuardSettings,
): OpenVpnBufferGuardSettings {
  return {
    ...settings,
    node_id: nodeId,
    watch_units:
      settings.watch_units && settings.watch_units.length > 0
        ? sortUnits(settings.watch_units)
        : [...DEFAULT_WATCH_UNITS],
  }
}

function lastEventSummary(event: OpenVpnBufferGuardEvent | null): { title: string; detail: string } | null {
  if (!event) return null

  const when = formatDateTime(event.created_at)
  const unit = event.unit || 'unit?'
  const total = event.error_count
  const window = event.window_seconds

  const baseTitle = `Последнее событие: ${total} ENOBUFS за ${window} с в ${unit}`

  const parts: string[] = []
  if (event.common_name) {
    parts.push(`клиент ${event.common_name}${event.real_address ? ` (${event.real_address})` : ''}`)
  }

  const modeRu: Record<OpenVpnBufferGuardMode, string> = {
    notify: 'режим notify (только уведомление)',
    kill: 'режим kill (отключение клиента)',
    kill_restart: 'режим kill_restart (отключение + перезапуск)',
    kill_restart_temp_ban: 'режим kill_restart_temp_ban (отключение + перезапуск + бан)',
  }

  parts.push(modeRu[event.mode])

  const resultRu: Record<string, string> = {
    banned: 'клиент заблокирован временно',
    restarted: 'сервер перезапущен',
    killed: 'клиент отключён',
    notified: 'порог превышен, действия не применялись',
    failed: 'автоматические действия не удались',
  }

  if (event.result && resultRu[event.result]) {
    parts.push(resultRu[event.result])
  }

  if (event.manual) {
    parts.push('ручной запуск')
  }

  if (event.ban_expires_at) {
    parts.push(`бан до ${formatDateTime(event.ban_expires_at)}`)
  }

  const detail = `${when} · ${parts.join(' · ')}`
  return { title: baseTitle, detail }
}

export default function OpenVpnBufferGuardCard({
  activeNodeId,
  nodeName,
  disabled = false,
}: OpenVpnBufferGuardCardProps) {
  const { success, warning: notifyWarning, error: notifyError } = useNotifications()

  const [settings, setSettings] = useState<OpenVpnBufferGuardSettings | null>(null)
  const [draft, setDraft] = useState<OpenVpnBufferGuardSettings | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [scanBusy, setScanBusy] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [events, setEvents] = useState<OpenVpnBufferGuardEvent[]>([])
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const busy = loading || saving || scanBusy
  const controlsDisabled = disabled || busy || activeNodeId == null || loadError != null

  const dirty = useMemo(() => {
    if (!settings || !draft) return false
    const simpleFields: (keyof OpenVpnBufferGuardSettings)[] = [
      'enabled',
      'mode',
      'threshold_count',
      'window_seconds',
      'escalate_after_seconds',
      'cooldown_minutes',
      'temp_ban_minutes',
    ]
    for (const key of simpleFields) {
      if (settings[key] !== draft[key]) return true
    }
    if (sortUnits(settings.watch_units).join(',') !== sortUnits(draft.watch_units).join(',')) {
      return true
    }
    return false
  }, [settings, draft])

  const patchDraft = (patch: Partial<OpenVpnBufferGuardSettings>) => {
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  const loadEvents = useCallback(
    async (nodeId: number) => {
      try {
        const data = await getBufferGuardEvents(nodeId)
        setEvents(data)
        setEventsError(null)
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : 'Не удалось загрузить последние события Buffer Guard'
        setEventsError(message)
        notifyError(message)
      }
    },
    [notifyError],
  )

  const loadSettings = useCallback(
    async (nodeId: number) => {
      setLoading(true)
      setLoadError(null)
      try {
        const data = await getBufferGuardSettings(nodeId)
        const normalized = normalizeSettingsForNode(nodeId, data)
        setSettings(normalized)
        setDraft(normalized)
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : 'Не удалось загрузить настройки OpenVPN Buffer Guard'
        setLoadError(message)
        notifyError(message)
      } finally {
        setLoading(false)
      }
    },
    [notifyError],
  )

  const reloadAll = useCallback(
    async (nodeId: number) => {
      await loadSettings(nodeId)
      await loadEvents(nodeId)
    },
    [loadEvents, loadSettings],
  )

  useEffect(() => {
    if (activeNodeId == null) {
      setSettings(null)
      setDraft(null)
      setEvents([])
      setLoadError(null)
      setEventsError(null)
      return
    }
    void reloadAll(activeNodeId)
  }, [activeNodeId, reloadAll])

  const handleSave = async () => {
    if (!draft || activeNodeId == null) return
    if (controlsDisabled) return
    setSaving(true)
    try {
      const payload: OpenVpnBufferGuardSettings = {
        ...draft,
        node_id: activeNodeId,
        watch_units:
          draft.watch_units && draft.watch_units.length > 0
            ? sortUnits(draft.watch_units)
            : [...DEFAULT_WATCH_UNITS],
      }
      const updated = await putBufferGuardSettings(payload)
      const normalized = normalizeSettingsForNode(activeNodeId, updated)
      setSettings(normalized)
      setDraft(normalized)
      success('Настройки OpenVPN Buffer Guard сохранены')
    } catch (err) {
      notifyError(
        err instanceof ApiError
          ? err.message
          : 'Не удалось сохранить настройки OpenVPN Buffer Guard',
      )
    } finally {
      setSaving(false)
    }
  }

  const handleScan = async () => {
    if (activeNodeId == null || disabled) return
    setScanBusy(true)
    try {
      const results = (await scanBufferGuard(activeNodeId)) as OpenVpnBufferGuardScanResult[]
      const triggered =
        Array.isArray(results) && results.length > 0
          ? results.some((r) => r && typeof r === 'object' && r.threshold_exceeded)
          : false
      if (triggered) {
        notifyWarning(
          'Порог ENOBUFS превышен — проверьте последний блок ниже и логи OpenVPN. Ручной запуск не применяет действия.',
        )
      } else {
        success('Проверка Buffer Guard выполнена: превышений порога не найдено')
      }
      await loadEvents(activeNodeId)
    } catch (err) {
      notifyError(
        err instanceof ApiError ? err.message : 'Не удалось выполнить проверку Buffer Guard',
      )
    } finally {
      setScanBusy(false)
    }
  }

  const handleToggleUnit = (unit: string, checked: boolean | 'indeterminate') => {
    if (!draft) return
    const nextChecked = checked === 'indeterminate' ? false : checked
    const current = sortUnits(draft.watch_units)
    let next: string[]
    if (nextChecked) {
      if (!current.includes(unit)) next = sortUnits([...current, unit])
      else next = current
    } else {
      next = current.filter((u) => u !== unit)
      if (next.length === 0) {
        notifyError('Нужно выбрать хотя бы один unit для наблюдения')
        return
      }
    }
    patchDraft({ watch_units: next })
  }

  const currentEvent = events.length > 0 ? events[0] : null
  const eventSummary = lastEventSummary(currentEvent)

  const cardDisabled = activeNodeId == null

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <div className="flex gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ShieldAlert className="h-4 w-4" />
          </div>
          <div className="min-w-0 space-y-1">
            <CardTitle className="text-base">OpenVPN Buffer Guard</CardTitle>
            <CardDescription className="mt-1">
              Защита общего UDP-сокета OpenVPN от лавины ошибок ENOBUFS при shared UDP / DCO и
              шумных клиентах. Сканирует журналы OpenVPN и по порогу реагирует на «засоряющие»
              подключения.
            </CardDescription>
            {nodeName && (
              <p className="mt-1 text-xs text-muted-foreground">
                Активный узел: <span className="font-medium text-foreground">{nodeName}</span>
              </p>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 border-t px-4 py-4 sm:px-5">
        <SettingsAlert variant="warning">
          <p className="text-xs leading-relaxed">
            Buffer Guard не чинит саму причину ENOBUFS (лимиты ядра, DCO, шумные клиенты), а только
            помогает не уронить общий UDP-сокет. Настраивайте пороги аккуратно и сначала используйте
            режим «Только уведомлять».
          </p>
        </SettingsAlert>

        {cardDisabled && (
          <p className="text-xs text-muted-foreground">
            Выберите VPN-узел вверху, чтобы настроить Buffer Guard.
          </p>
        )}

        {loadError && !cardDisabled && (
          <div className="space-y-3">
            <SettingsAlert variant="danger" title="Не удалось загрузить настройки Buffer Guard">
              {loadError}
            </SettingsAlert>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => activeNodeId != null && void reloadAll(activeNodeId)}
            >
              Повторить загрузку
            </Button>
          </div>
        )}

        {!cardDisabled && !loadError && draft && (
          <>
            <div
              className={cn(
                'flex items-start justify-between gap-4 rounded-xl border bg-card/50 p-4 transition-colors',
                draft.enabled && 'border-emerald-500/40 bg-emerald-500/5',
              )}
            >
              <div className="min-w-0 space-y-1">
                <Label htmlFor="openvpn-buffer-guard-enabled" className="cursor-pointer font-medium">
                  Включить Buffer Guard
                </Label>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  При включении автоматические действия (kill / restart / временный бан) применяются
                  только при фоновых проходах. Ручная проверка ниже всегда &mdash; только анализ.
                </p>
              </div>
              <div className="flex flex-col items-end gap-1">
                <Switch
                  id="openvpn-buffer-guard-enabled"
                  checked={draft.enabled}
                  onCheckedChange={(checked) => patchDraft({ enabled: checked })}
                  disabled={controlsDisabled}
                  aria-label={
                    draft.enabled ? 'Buffer Guard включён' : 'Buffer Guard выключен'
                  }
                />
                <span className="text-[11px] text-muted-foreground">
                  {draft.enabled ? 'Вкл.' : 'Выкл.'}
                </span>
              </div>
            </div>

            <div className="space-y-2 rounded-xl border bg-muted/20 p-4">
              <Label className="text-xs text-muted-foreground">Режим действий</Label>
              <div className="grid gap-3 md:grid-cols-[minmax(0,240px),minmax(0,1fr)]">
                <Select
                  value={draft.mode}
                  onValueChange={(value) => patchDraft({ mode: value as OpenVpnBufferGuardMode })}
                  disabled={controlsDisabled}
                >
                  <SelectTrigger className="h-9 w-full md:w-60">
                    <SelectValue placeholder="Выберите режим" />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(MODE_LABELS) as OpenVpnBufferGuardMode[]).map((mode) => (
                      <SelectItem key={mode} value={mode}>
                        {MODE_LABELS[mode]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {MODE_HINTS[draft.mode]}
                </p>
              </div>
            </div>

            <div className="space-y-2 rounded-xl border bg-muted/10 p-3">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 text-left text-sm font-medium"
                onClick={() => setAdvancedOpen((v) => !v)}
              >
                <span className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-primary" />
                  Дополнительно
                </span>
                <span className="text-xs text-muted-foreground">
                  {advancedOpen ? 'Скрыть параметры' : 'Показать параметры'}
                </span>
              </button>
              {advancedOpen && (
                <div className="mt-3 space-y-4 border-t pt-3">
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="buffer-guard-threshold" className="text-xs text-muted-foreground">
                        Порог ENOBUFS за окно
                      </Label>
                      <div className="flex items-center gap-2">
                        <Input
                          id="buffer-guard-threshold"
                          type="number"
                          min={10}
                          max={1_000_000}
                          className="h-9 w-32"
                          value={draft.threshold_count}
                          disabled={controlsDisabled}
                          onChange={(e) =>
                            patchDraft({
                              threshold_count: Math.max(
                                10,
                                Math.min(1_000_000, Number(e.target.value) || 10),
                              ),
                            })
                          }
                        />
                        <span className="text-xs text-muted-foreground">ENOBUFS за окно</span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="buffer-guard-window" className="text-xs text-muted-foreground">
                        Длина окна в секундах
                      </Label>
                      <div className="flex items-center gap-2">
                        <Input
                          id="buffer-guard-window"
                          type="number"
                          min={10}
                          max={600}
                          className="h-9 w-24"
                          value={draft.window_seconds}
                          disabled={controlsDisabled}
                          onChange={(e) =>
                            patchDraft({
                              window_seconds: Math.max(
                                10,
                                Math.min(600, Number(e.target.value) || 10),
                              ),
                            })
                          }
                        />
                        <span className="text-xs text-muted-foreground">секунд</span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label
                        htmlFor="buffer-guard-escalate"
                        className="text-xs text-muted-foreground"
                      >
                        Задержка перед эскалацией
                      </Label>
                      <div className="flex items-center gap-2">
                        <Input
                          id="buffer-guard-escalate"
                          type="number"
                          min={5}
                          max={300}
                          className="h-9 w-24"
                          value={draft.escalate_after_seconds}
                          disabled={controlsDisabled}
                          onChange={(e) =>
                            patchDraft({
                              escalate_after_seconds: Math.max(
                                5,
                                Math.min(300, Number(e.target.value) || 5),
                              ),
                            })
                          }
                        />
                        <span className="text-xs text-muted-foreground">
                          сек до повтора проверки перед restart
                        </span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label
                        htmlFor="buffer-guard-cooldown"
                        className="text-xs text-muted-foreground"
                      >
                        Пауза между автоматическими срабатываниями
                      </Label>
                      <div className="flex items-center gap-2">
                        <Input
                          id="buffer-guard-cooldown"
                          type="number"
                          min={1}
                          max={1440}
                          className="h-9 w-24"
                          value={draft.cooldown_minutes}
                          disabled={controlsDisabled}
                          onChange={(e) =>
                            patchDraft({
                              cooldown_minutes: Math.max(
                                1,
                                Math.min(1440, Number(e.target.value) || 1),
                              ),
                            })
                          }
                        />
                        <span className="text-xs text-muted-foreground">минут после события</span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label
                        htmlFor="buffer-guard-temp-ban"
                        className="text-xs text-muted-foreground"
                      >
                        Временный бан клиента
                      </Label>
                      <div className="flex items-center gap-2">
                        <Input
                          id="buffer-guard-temp-ban"
                          type="number"
                          min={5}
                          max={10_080}
                          className="h-9 w-24"
                          value={draft.temp_ban_minutes}
                          disabled={controlsDisabled || draft.mode !== 'kill_restart_temp_ban'}
                          onChange={(e) =>
                            patchDraft({
                              temp_ban_minutes: Math.max(
                                5,
                                Math.min(10_080, Number(e.target.value) || 5),
                              ),
                            })
                          }
                        />
                        <span className="text-xs text-muted-foreground">минут блокировки</span>
                      </div>
                      <p className="text-[11px] leading-snug text-muted-foreground">
                        Используется только в режиме временного бана; клиенты заносятся в
                        banned_clients и автоматически разбаниваются после истечения времени.
                      </p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Какие юниты смотреть</Label>
                    <div className="grid gap-2 md:grid-cols-2">
                      {Object.keys(WATCH_UNIT_LABELS).map((unit) => (
                        <label
                          key={unit}
                          className="flex items-start gap-2 rounded-lg border bg-background px-3 py-2 text-xs"
                        >
                          <Checkbox
                            className="mt-0.5"
                            checked={draft.watch_units.includes(unit)}
                            disabled={controlsDisabled}
                            onCheckedChange={(checked) => handleToggleUnit(unit, checked)}
                            aria-label={`Следить за юнитом ${unit}`}
                          />
                          <span className="leading-snug">
                            <span className="font-medium">{WATCH_UNIT_LABELS[unit]}</span>
                            <span className="mt-0.5 block text-[11px] text-muted-foreground">
                              Смотрим journalctl этого OpenVPN-сервиса на ENOBUFS в последнем окне.
                            </span>
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-xs text-muted-foreground">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-1.5">
                  <Timer className="h-3.5 w-3.5" />
                  <span>
                    Последнее обновление настроек:{' '}
                    <span className="text-foreground">
                      {settings?.updated_at ? formatDateTime(settings.updated_at) : 'ещё не было'}
                    </span>
                  </span>
                </div>
                {eventSummary && (
                  <div className="flex items-start gap-1.5">
                    {currentEvent?.result === 'banned' ? (
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 text-amber-500" />
                    ) : (
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 text-emerald-500" />
                    )}
                    <div className="space-y-0.5">
                      <p className="font-medium text-foreground">{eventSummary.title}</p>
                      <p className="text-[11px] text-muted-foreground">{eventSummary.detail}</p>
                    </div>
                  </div>
                )}
                {eventsError && !eventSummary && (
                  <p className="text-[11px] text-destructive">
                    Не удалось загрузить последние события: {eventsError}
                  </p>
                )}
                {!eventSummary && !eventsError && (
                  <p className="text-[11px] text-muted-foreground">
                    Ещё не было срабатываний Buffer Guard для этого узла.
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => void handleScan()}
                  disabled={disabled || activeNodeId == null || scanBusy}
                >
                  <Zap className={cn('h-4 w-4', scanBusy && 'animate-pulse')} />
                  {scanBusy ? 'Проверка…' : 'Проверить сейчас'}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  className="gap-1.5"
                  disabled={!dirty || controlsDisabled}
                  onClick={() => void handleSave()}
                >
                  Сохранить
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

