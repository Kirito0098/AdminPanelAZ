import { useCallback, useEffect, useId, useState } from 'react'
import {
  ApiError,
  applyOpenVpnDco,
  applyOpenVpnMtu,
  applyOpenVpnPatch,
  applyOpenVpnProtocols,
  applyOpenVpnTuning,
  getOpenVpnTuning,
} from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { createLatestRequest } from '@/lib/latestRequest'
import type { OpenVpnToggleState, OpenVpnTuningState } from '@/types'

const PATCH_OPTIONS = [
  { value: '1', label: '1 — не устанавливать (снять патч)' },
  { value: '2', label: '2 — Random (по умолчанию)' },
  { value: '3', label: '3 — Strong' },
  { value: '4', label: '4 — Error-Free (для роутеров)' },
]

const TOGGLE_HINT: Record<OpenVpnToggleState, string> = {
  on: 'включено во всех конфигах',
  off: 'выключено во всех конфигах',
  mixed: 'в разных конфигах по-разному',
  unknown: 'в конфигах нет нужных строк',
}

function ToggleStateBadge({ value }: { value: OpenVpnToggleState }) {
  if (value === 'on') return <Badge variant="outline" className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300">вкл</Badge>
  if (value === 'off') return <Badge variant="outline">выкл</Badge>
  if (value === 'mixed') return <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-300">разнобой</Badge>
  return <Badge variant="outline" className="text-muted-foreground">нет данных</Badge>
}

type OpenVpnTuningCardProps = {
  activeNodeId: number | null
  nodeName?: string | null
  disabled?: boolean
}

export default function OpenVpnTuningCard({ activeNodeId, nodeName, disabled = false }: OpenVpnTuningCardProps) {
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const idBase = useId()
  const [state, setState] = useState<OpenVpnTuningState | null>(null)
  const [duplicate, setDuplicate] = useState(true)
  const [logs, setLogs] = useState(false)
  const [mtuOpenvpn, setMtuOpenvpn] = useState('1420')
  const [mtuWireguard, setMtuWireguard] = useState('1420')
  const [dco, setDco] = useState(true)
  const [patchAlgorithm, setPatchAlgorithm] = useState('2')
  const [protocols, setProtocols] = useState<Record<string, boolean>>({})
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [requests] = useState(() => createLatestRequest<number | null>(null))

  const syncFromState = useCallback((data: OpenVpnTuningState) => {
    setState(data)
    setDuplicate(data.duplicate_cn === 'on')
    setLogs(data.logs === 'on')
    setDco(data.dco === 'on')
    setMtuOpenvpn(String(typeof data.mtu_openvpn === 'number' ? data.mtu_openvpn : 1420))
    setMtuWireguard(String(typeof data.mtu_wireguard === 'number' ? data.mtu_wireguard : 1420))
    setProtocols(Object.fromEntries(data.protocols.map((item) => [item.unit, item.enabled === true])))
  }, [])

  const load = useCallback(async () => {
    requests.reset(activeNodeId)
    setState(null)
    setLoadError(null)
    setLoading(false)
    if (activeNodeId == null) return
    const isCurrent = requests.begin()
    setLoading(true)
    try {
      const data = await getOpenVpnTuning()
      if (isCurrent()) syncFromState(data)
    } catch (err) {
      if (!isCurrent()) return
      setLoadError(err instanceof ApiError ? err.message : 'Не удалось прочитать настройки OpenVPN')
    } finally {
      if (isCurrent()) setLoading(false)
    }
  }, [activeNodeId, requests, syncFromState])

  useEffect(() => {
    void load()
  }, [load])

  const initialDuplicate = state ? state.duplicate_cn === 'on' : true
  const initialLogs = state ? state.logs === 'on' : false
  const dirty = state != null && (duplicate !== initialDuplicate || logs !== initialLogs)
  const controlsDisabled = disabled || loading || saving || state == null

  function askApply() {
    confirm({
      title: 'Применить настройки OpenVPN?',
      description:
        'Панель поправит server conf и перезапустит включённые службы OpenVPN — все подключённые клиенты переподключатся. Если служба не поднимется, конфиги вернутся как были.',
      confirmLabel: 'Применить',
      destructive: true,
      onConfirm: async () => {
        const isCurrent = requests.begin()
        setSaving(true)
        try {
          const updated = await applyOpenVpnTuning(duplicate, logs)
          success('Настройки OpenVPN применены')
          if (isCurrent()) syncFromState(updated)
          for (const warning of updated.warnings) notifyError(warning)
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось применить настройки OpenVPN')
          if (isCurrent()) void load()
        } finally {
          setSaving(false)
        }
      },
    })
  }

  const runAction = useCallback(
    async (label: string, action: () => Promise<OpenVpnTuningState>, doneMessage: string) => {
      const isCurrent = requests.begin()
      setBusyAction(label)
      try {
        const updated = await action()
        success(doneMessage)
        if (isCurrent()) syncFromState(updated)
        for (const warning of updated.warnings) notifyError(warning)
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : `Не удалось выполнить: ${label}`)
        if (isCurrent()) void load()
      } finally {
        setBusyAction(null)
      }
    },
    [load, notifyError, requests, success, syncFromState],
  )

  const mtuChanges = (() => {
    if (!state) return {} as { openvpn?: number; wireguard?: number }
    const changes: { openvpn?: number; wireguard?: number } = {}
    const ovpn = Number(mtuOpenvpn)
    const wg = Number(mtuWireguard)
    if (ovpn !== state.mtu_openvpn) changes.openvpn = ovpn
    if (wg !== state.mtu_wireguard) changes.wireguard = wg
    return changes
  })()
  const mtuDirty = Object.keys(mtuChanges).length > 0

  const askMtu = () => {
    if (!mtuDirty) return
    const parts: string[] = []
    if (mtuChanges.openvpn != null) parts.push(`OpenVPN — ${mtuChanges.openvpn}`)
    if (mtuChanges.wireguard != null) parts.push(`WireGuard — ${mtuChanges.wireguard}`)
    confirm({
      title: 'Применить MTU?',
      description: `${parts.join(', ')}. OpenVPN и WireGuard задаются отдельно: OpenVPN — tun-mtu в server conf, WireGuard — MTU = в живых конфигах и шаблонах. Перезапустятся только затронутые службы, клиенты переподключатся.`,
      confirmLabel: 'Применить',
      destructive: true,
      onConfirm: () =>
        runAction('mtu', () => applyOpenVpnMtu(mtuChanges), 'MTU применён'),
    })
  }

  const askDco = () => {
    confirm({
      title: dco ? 'Включить OpenVPN DCO?' : 'Выключить OpenVPN DCO?',
      description: dco
        ? 'DCO снижает нагрузку на CPU, но работает только с AES-128-GCM, AES-256-GCM и CHACHA20-POLY1305. Клиенты, у которых остались старые CBC-шифры, не подключатся.'
        : 'DCO будет выключен: вернётся обычный режим OpenVPN с CBC-шифрами. Службы OpenVPN перезапустятся, клиенты переподключатся.',
      confirmLabel: dco ? 'Включить DCO' : 'Выключить DCO',
      destructive: true,
      onConfirm: () => runAction('dco', () => applyOpenVpnDco(dco), dco ? 'DCO включён' : 'DCO выключен'),
    })
  }

  const askPatch = () => {
    confirm({
      title: `Патч OpenVPN: вариант ${patchAlgorithm}`,
      description:
        'Скрипт AntiZapret скачает исходники OpenVPN, соберёт их с патчем и перезапустит службы — это несколько минут, и всё это время OpenVPN на узле недоступен. Узел должен иметь доступ в интернет и свободное место. Вкладку не закрывайте: панель ждёт завершения (до 30 минут).',
      confirmLabel: 'Запустить',
      destructive: true,
      confirmPhrase: nodeName ?? undefined,
      confirmPhraseLabel: nodeName ? `Введите имя узла «${nodeName}»` : undefined,
      onConfirm: () =>
        runAction('patch', () => applyOpenVpnPatch(Number(patchAlgorithm)), 'Патч OpenVPN применён'),
    })
  }

  const changedProtocols = Object.fromEntries(
    Object.entries(protocols).filter(([unit, enabled]) => {
      const current = state?.protocols.find((item) => item.unit === unit)?.enabled === true
      return enabled !== current
    }),
  )
  const protocolsDirty = Object.keys(changedProtocols).length > 0

  const askProtocols = () => {
    const list = Object.entries(changedProtocols)
      .map(([unit, enabled]) => `${unit} — ${enabled ? 'включить' : 'выключить'}`)
      .join('; ')
    confirm({
      title: 'Изменить протоколы узла?',
      description: `${list}. Выключение протокола останавливает его службу: клиенты этого протокола отключатся и не смогут подключиться, пока протокол не включат снова. Профили на диске не удаляются.`,
      confirmLabel: 'Применить',
      destructive: true,
      confirmPhrase: nodeName ?? undefined,
      confirmPhraseLabel: nodeName ? `Введите имя узла «${nodeName}»` : undefined,
      onConfirm: () =>
        runAction('protocols', () => applyOpenVpnProtocols(changedProtocols), 'Протоколы обновлены'),
    })
  }

  const mtuLabel = (value: number | 'mixed' | null | undefined) =>
    value === null || value === undefined ? '—' : value === 'mixed' ? 'разнобой' : `${value}`

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">OpenVPN: профили, логи и состояние установки</CardTitle>
        <CardDescription className="mt-1">
          Что установщик AntiZapret настраивает в <code>openvpn/server/*.conf</code> и службах. Слева —
          поведение подключений, справа — обслуживание узла; правки применяются с откатом конфигов.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 border-t px-4 py-4 sm:px-5">
        {activeNodeId == null && (
          <p className="text-xs text-muted-foreground">
            Выберите VPN-узел вверху, чтобы увидеть состояние OpenVPN.
          </p>
        )}

        {loadError && activeNodeId != null && (
          <div className="space-y-3">
            <SettingsAlert variant="danger" title="Не удалось прочитать настройки OpenVPN">
              {loadError}
            </SettingsAlert>
            <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void load()}>
              Повторить загрузку
            </Button>
          </div>
        )}

        {activeNodeId != null && !loadError && state != null && (
          <>
            {state.warnings.map((warning) => (
              <SettingsAlert key={warning} variant="warning" title="Обратите внимание">
                {warning}
              </SettingsAlert>
            ))}

            <div className="grid gap-5 xl:grid-cols-2">
              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Профили и логи
                </p>
              <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
                <div className="min-w-0 space-y-1">
                  <Label htmlFor={`${idBase}-duplicate`} className="cursor-pointer font-medium">
                    Несколько устройств с одним профилем
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    <code>duplicate-cn</code> — разрешает подключаться вторым устройством с тем же
                    <code> *.ovpn</code>. Выключено: новое подключение выбивает предыдущее.
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Сейчас: <ToggleStateBadge value={state.duplicate_cn} /> {TOGGLE_HINT[state.duplicate_cn]}
                  </p>
                </div>
                <Switch
                  id={`${idBase}-duplicate`}
                  checked={duplicate}
                  disabled={controlsDisabled}
                  onCheckedChange={setDuplicate}
                />
              </div>

              <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
                <div className="min-w-0 space-y-1">
                  <Label htmlFor={`${idBase}-logs`} className="cursor-pointer font-medium">
                    Подробные логи и статус OpenVPN
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    <code>verb 4</code>, <code>log-append</code>, <code>status</code> — нужны для разбора
                    жалоб и для OpenVPN Buffer Guard.
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Сейчас: <ToggleStateBadge value={state.logs} /> {TOGGLE_HINT[state.logs]}
                  </p>
                </div>
                <Switch id={`${idBase}-logs`} checked={logs} disabled={controlsDisabled} onCheckedChange={setLogs} />
              </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" size="sm" disabled={controlsDisabled || !dirty || saving} onClick={askApply}>
                Применить
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={controlsDisabled || !dirty || saving}
                onClick={() => {
                  if (state) syncFromState(state)
                }}
              >
                Сбросить
              </Button>
              <Button type="button" variant="outline" size="sm" disabled={loading || saving} onClick={() => void load()}>
                Обновить состояние
              </Button>
            </div>

                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Состояние</p>
                  <p className="text-[11px] leading-snug text-muted-foreground">
                    Что реально стоит в конфигах узла. «Разнобой» — значения в файлах различаются, «нет данных» —
                    нужной строки в конфиге нет.
                  </p>
                </div>
              <dl className="grid gap-2.5 text-xs sm:grid-cols-2">
                <div className="space-y-0.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="font-medium">MTU OpenVPN</dt>
                    <dd className="font-mono">{mtuLabel(state.mtu_openvpn)}</dd>
                  </div>
                  <dd className="text-[11px] leading-snug text-muted-foreground">
                    <code>tun-mtu</code> в server conf. 1420 — обычное значение; ниже ставят, если у провайдера
                    теряются крупные пакеты (обрывы загрузок, «зависшие» соединения)
                  </dd>
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="font-medium">MTU WireGuard</dt>
                    <dd className="font-mono">{mtuLabel(state.mtu_wireguard)}</dd>
                  </div>
                  <dd className="text-[11px] leading-snug text-muted-foreground">
                    <code>MTU =</code> в живом конфиге и шаблоне. Значение независимо от OpenVPN; при одинаковом
                    канале их обычно держат равными
                  </dd>
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="font-medium">DCO</dt>
                    <dd><ToggleStateBadge value={state.dco} /></dd>
                  </div>
                  <dd className="text-[11px] leading-snug text-muted-foreground">
                    Аппаратное ускорение OpenVPN. <span className="font-mono">on</span> — только GCM/CHACHA20,
                    <span className="font-mono"> off</span> — с CBC-шифрами
                  </dd>
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="font-medium">Автообновление списков</dt>
                    <dd>
                      <ToggleStateBadge value={state.update_timer ? 'on' : state.update_timer === false ? 'off' : 'unknown'} />
                    </dd>
                  </div>
                  <dd className="text-[11px] leading-snug text-muted-foreground">
                    <code>antizapret-update.timer</code> сам пересобирает списки AntiZapret по расписанию
                  </dd>
                </div>
                <div className="space-y-0.5 sm:col-span-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <dt className="font-medium">Патч антицензуры OpenVPN</dt>
                    <dd className="text-right">
                      {state.patch.in_use
                        ? 'установлен и используется'
                        : state.patch.custom_binary
                          ? 'собран, но служба запускает системный бинарник'
                          : 'не установлен'}
                    </dd>
                  </div>
                  <dd className="text-[11px] leading-snug text-muted-foreground">
                    Обфускация UDP-пакетов OpenVPN (сборка в <code>/usr/local/sbin/openvpn</code>). «Собран, но
                    служба запускает системный бинарник» — патч фактически не работает: служба берёт{' '}
                    <code>/usr/sbin/openvpn</code>
                    {state.patch.unit_exec && (
                      <span className="block font-mono text-[10px] text-muted-foreground/70">
                        ExecStart: {state.patch.unit_exec}
                      </span>
                    )}
                  </dd>
                </div>
            </dl>

            </div>

            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Обслуживание</p>
              <div className="space-y-3">
              <div className="space-y-2">
                <Label>MTU</Label>
                <div className="flex flex-wrap items-end gap-3">
                  <div className="space-y-1">
                    <Label htmlFor={`${idBase}-mtu-openvpn`} className="text-xs text-muted-foreground">
                      OpenVPN
                    </Label>
                    <Input
                      id={`${idBase}-mtu-openvpn`}
                      type="number"
                      min={1280}
                      max={1420}
                      step={20}
                      value={mtuOpenvpn}
                      disabled={controlsDisabled}
                      onChange={(event) => setMtuOpenvpn(event.target.value)}
                      className="w-28"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`${idBase}-mtu-wg`} className="text-xs text-muted-foreground">
                      WireGuard
                    </Label>
                    <Input
                      id={`${idBase}-mtu-wg`}
                      type="number"
                      min={1280}
                      max={1420}
                      step={20}
                      value={mtuWireguard}
                      disabled={controlsDisabled}
                      onChange={(event) => setMtuWireguard(event.target.value)}
                      className="w-28"
                    />
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={controlsDisabled || busyAction !== null || !mtuDirty}
                    onClick={askMtu}
                  >
                    {busyAction === 'mtu' ? 'Применяется…' : 'Применить MTU'}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Два независимых значения: OpenVPN — <code>tun-mtu</code> в server conf, WireGuard —{' '}
                  <code>MTU =</code> в живых конфигах и шаблонах (установщик спрашивает один MTU и ставит оба).
                  Допустимо 1280–1420. Понижайте, если клиенты жалуются на обрывы загрузок или «зависшие»
                  соединения: так провайдер режет крупные пакеты.
                </p>
              </div>

              <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
                <div className="min-w-0 space-y-1">
                  <Label htmlFor={`${idBase}-dco`} className="cursor-pointer font-medium">
                    OpenVPN DCO
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Аппаратное ускорение OpenVPN: меньше нагрузка на CPU, но только GCM/CHACHA20 — клиенты со
                    старыми CBC-профилями отвалятся. Включайте, если сервер упирается в CPU при активном OpenVPN;
                    выключайте, если после включения часть клиентов не подключается или служба не стартует
                    (нужен OpenVPN 2.7 и поддержка DCO в ядре).
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Сейчас: <ToggleStateBadge value={state.dco} />
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <Switch id={`${idBase}-dco`} checked={dco} disabled={controlsDisabled} onCheckedChange={setDco} />
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={controlsDisabled || busyAction !== null || dco === (state.dco === 'on')}
                    onClick={askDco}
                  >
                    {busyAction === 'dco' ? 'Применяется…' : 'Применить'}
                  </Button>
                </div>
              </div>

              <div className="space-y-2 rounded-lg border p-3">
                <Label>Патч антицензуры OpenVPN</Label>
                <div className="flex flex-wrap items-center gap-2">
                  <Select value={patchAlgorithm} onValueChange={setPatchAlgorithm} disabled={controlsDisabled}>
                    <SelectTrigger className="w-full sm:w-72">
                      <SelectValue placeholder="Вариант патча" />
                    </SelectTrigger>
                    <SelectContent>
                      {PATCH_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={controlsDisabled || busyAction !== null}
                    onClick={askPatch}
                  >
                    {busyAction === 'patch' ? 'Сборка… (до 30 минут)' : 'Запустить'}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Нужно, если провайдер блокирует OpenVPN по сигнатуре протокола — обычно это заметно только на UDP.
                  Скрипт скачает исходники, соберёт OpenVPN с обфускацией и перезапустит службы: несколько минут, и
                  всё это время OpenVPN на узле недоступен (нужен интернет и место на диске). Панель ждёт
                  завершения и показывает хвост вывода скрипта.
                </p>
                {state.patch_output && (
                  <pre className="max-h-40 overflow-auto rounded bg-muted/50 p-2 text-[10px] leading-relaxed">
                    {state.patch_output}
                  </pre>
                )}
              </div>

              <div className="space-y-2 rounded-lg border p-3">
                <Label>Протоколы узла</Label>
                <div className="grid gap-2 sm:grid-cols-2">
                  {state.protocols.map((protocol) => (
                    <div key={protocol.unit} className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-[11px]">
                        {protocol.unit.replace('openvpn-server@', '').replace('wg-quick@', 'wg: ')}
                      </span>
                      <Switch
                        checked={protocols[protocol.unit] ?? false}
                        disabled={controlsDisabled}
                        aria-label={protocol.unit}
                        onCheckedChange={(checked) =>
                          setProtocols((previous) => ({ ...previous, [protocol.unit]: checked }))
                        }
                      />
                    </div>
                  ))}
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={controlsDisabled || busyAction !== null || !protocolsDirty}
                  onClick={askProtocols}
                >
                  {busyAction === 'protocols' ? 'Применяется…' : 'Применить протоколы'}
                </Button>
                <p className="text-xs text-muted-foreground">
                  Выключайте протоколы, которыми не пользуетесь: так закрываются их порты и меньше поверхности для
                  атаки. Клиенты выключенного протокола отключатся и не подключатся, пока протокол не включат снова;
                  файлы профилей на диске остаются.
                </p>
              </div>
            </div>
            </div>
            </div>
          </>
        )}
      </CardContent>
      <ConfirmDialogHost dialogProps={dialogProps} />
    </Card>
  )
}

