import { useCallback, useEffect, useId, useState } from 'react'
import { ApiError, applyDnsServers, getDnsServers } from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useNotifications } from '@/context/NotificationContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { createLatestRequest } from '@/lib/latestRequest'
import type { DnsServersState } from '@/types'

type DnsServersCardProps = {
  activeNodeId: number | null
  disabled?: boolean
}

export default function DnsServersCard({ activeNodeId, disabled = false }: DnsServersCardProps) {
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const idBase = useId()
  const [state, setState] = useState<DnsServersState | null>(null)
  const [antizapret, setAntizapret] = useState('1')
  const [vpn, setVpn] = useState('2')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [requests] = useState(() => createLatestRequest<number | null>(null))

  const syncFromState = useCallback((data: DnsServersState) => {
    setState(data)
    setAntizapret(data.antizapret)
    setVpn(data.vpn)
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
      const data = await getDnsServers()
      if (isCurrent()) syncFromState(data)
    } catch (err) {
      if (!isCurrent()) return
      setLoadError(err instanceof ApiError ? err.message : 'Не удалось прочитать выбор DNS-серверов')
    } finally {
      if (isCurrent()) setLoading(false)
    }
  }, [activeNodeId, requests, syncFromState])

  useEffect(() => {
    void load()
  }, [load])

  const dirty = state != null && (antizapret !== state.antizapret || vpn !== state.vpn)
  const controlsDisabled = disabled || loading || saving || state == null || !state.supported

  function askApply() {
    const antizapretLabel =
      state?.antizapret_options.find((option) => option.value === antizapret)?.label ?? antizapret
    const vpnLabel = state?.vpn_options.find((option) => option.value === vpn)?.label ?? vpn
    confirm({
      title: 'Применить DNS-серверы?',
      description: `AntiZapret будет резолвить домены через «${antizapretLabel}», полный VPN — «${vpnLabel}». Резолверы kresd перезапустятся: несколько секунд клиенты не смогут разрешать имена.`,
      confirmLabel: 'Применить',
      destructive: true,
      alert: {
        variant: 'warning',
        title: 'Перезапуск DNS',
        children:
          'Клиенты могут помнить прежний ответ до суток — после смены переподключите VPN или перезапустите приложение.',
      },
      onConfirm: async () => {
        const isCurrent = requests.begin()
        setSaving(true)
        try {
          const updated = await applyDnsServers(Number(antizapret), Number(vpn))
          success('DNS-серверы применены, резолверы перезапущены')
          if (isCurrent()) syncFromState(updated)
          for (const warning of updated.warnings) notifyError(warning)
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось применить DNS-серверы')
          if (isCurrent()) void load()
        } finally {
          setSaving(false)
        }
      },
    })
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">DNS-серверы</CardTitle>
        <CardDescription className="mt-1">
          Какими резолверами AntiZapret разрешает домены. Выбор пишется прямо в{' '}
          <code>/etc/knot-resolver/kresd.conf</code> и сохраняется в setup, поэтому его не сбрасывает
          повторный setup.sh. Если выбранные DNS заблокированы у провайдера — переключитесь на другой вариант.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 border-t px-4 py-4 sm:px-5">
        {activeNodeId == null && (
          <p className="text-xs text-muted-foreground">Выберите VPN-узел вверху, чтобы настроить DNS-серверы.</p>
        )}

        {loadError && activeNodeId != null && (
          <div className="space-y-3">
            <SettingsAlert variant="danger" title="Не удалось прочитать выбор DNS-серверов">
              {loadError}
            </SettingsAlert>
            <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void load()}>
              Повторить загрузку
            </Button>
          </div>
        )}

        {activeNodeId != null && !loadError && state != null && (
          <>
            {!state.supported && (
              <SettingsAlert variant="warning" title="AntiZapret на узле не поддерживает выбор DNS">
                В <code>/etc/knot-resolver/kresd.conf</code> нет строк <code>local antizapret_dns</code> /{' '}
                <code>local vpn_dns</code> — обновите AntiZapret-VPN на узле.
              </SettingsAlert>
            )}

            {state.warnings.map((warning) => (
              <SettingsAlert key={warning} variant="warning" title="Выбор в setup расходится с резолвером">
                {warning}
              </SettingsAlert>
            ))}

            <div className="space-y-1.5">
              <Label htmlFor={`${idBase}-antizapret`}>AntiZapret VPN (antizapret-*)</Label>
              <Select value={antizapret} onValueChange={setAntizapret} disabled={controlsDisabled}>
                <SelectTrigger id={`${idBase}-antizapret`} className="w-full">
                  <SelectValue placeholder="DNS-сервер" />
                </SelectTrigger>
                <SelectContent>
                  {state.antizapret_options.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.value}) {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Резолвер <code>kresd@1</code>, файл <code>/etc/knot-resolver/kresd.conf</code>
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor={`${idBase}-vpn`}>Полный VPN (vpn-*)</Label>
              <Select value={vpn} onValueChange={setVpn} disabled={controlsDisabled}>
                <SelectTrigger id={`${idBase}-vpn`} className="w-full">
                  <SelectValue placeholder="DNS-сервер" />
                </SelectTrigger>
                <SelectContent>
                  {state.vpn_options.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.value}) {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Резолвер <code>kresd@2</code>. Вариант 1 отдаёт полному VPN тот же DNS, что AntiZapret, вариант 2
                оставляет Cloudflare/Quad9 и разрешает клиентам свой DNS
              </p>
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
            </div>
          </>
        )}
      </CardContent>
      <ConfirmDialogHost dialogProps={dialogProps} />
    </Card>
  )
}

