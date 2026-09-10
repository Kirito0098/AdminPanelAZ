import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ApiError } from '@/api/client'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import { createTgUnlockCode, getTgUnlockCodes, revokeTgUnlockCode, type UnlockCodeProtocol } from '@/tg-mini/api'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import { formatDateTime } from '@/lib/datetime'
import {
  isUnlockCodeExhausted,
  unlockCodeRedeemedCount,
  unlockCodeStatusLabel,
} from '@/lib/unlockCodeStatus'
import { cn } from '@/lib/utils'
import { vpnTypeBadgeClass, vpnTypeLabel } from '@/tg-mini/lib/vpnLabels'
import type { UnlockCodeRecord } from '@/types'
import { Ban, CalendarClock, Copy, KeyRound, Loader2, RefreshCw, ShieldCheck, Trash2, Users } from 'lucide-react'
import { Navigate } from 'react-router-dom'

const ALL_PROTOCOLS: UnlockCodeProtocol[] = ['openvpn', 'wireguard', 'amneziawg2']

function protocolLabel(protocol: UnlockCodeProtocol) {
  return vpnTypeLabel(protocol)
}

function toEndOfDayIso(value: string) {
  if (!value) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 23, 59, 59, 999)
  return date.toISOString()
}

type Feedback = { tone: 'success' | 'error' | 'info'; text: string }

function UnlockCodesSkeleton() {
  return (
    <div className="tg-mini-dashboard space-y-4" aria-busy="true" aria-label="Загрузка unlock-кодов">
      <div className="tg-mini-skeleton" style={{ height: '2.5rem' }} />
      <div className="tg-mini-skeleton tg-mini-skeleton-section" />
      <div className="tg-mini-skeleton tg-mini-skeleton-section" />
    </div>
  )
}

function FeedbackBanner({ feedback }: { feedback: Feedback }) {
  return (
    <div
      className={cn(
        'tg-mini-feedback',
        feedback.tone === 'success' && 'is-success',
        feedback.tone === 'error' && 'is-error',
        feedback.tone === 'info' && 'is-info',
      )}
      role="status"
    >
      {feedback.tone === 'error' ? <Ban size={18} className="shrink-0" aria-hidden /> : <ShieldCheck size={18} className="shrink-0 opacity-80" aria-hidden />}
      <p className="text-sm leading-snug">{feedback.text}</p>
    </div>
  )
}

function ProtocolPill({ protocol }: { protocol: UnlockCodeProtocol }) {
  return (
    <span className={cn('tg-mini-protocol-badge', vpnTypeBadgeClass(protocol))}>{protocolLabel(protocol)}</span>
  )
}

export default function UnlockCodes() {
  const { isAdmin, features } = useTgAuth()
  const [codes, setCodes] = useState<UnlockCodeRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [revokingId, setRevokingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [createdCode, setCreatedCode] = useState<UnlockCodeRecord | null>(null)
  const [grantDays, setGrantDays] = useState('30')
  const [mode, setMode] = useState<'single' | 'multi'>('single')
  const [maxRedemptions, setMaxRedemptions] = useState('10')
  const [codeExpiresAt, setCodeExpiresAt] = useState('')
  const [selectedProtocols, setSelectedProtocols] = useState<UnlockCodeProtocol[]>([])

  const availableProtocols = useMemo(
    () =>
      ALL_PROTOCOLS.filter((protocol) => {
        if (protocol === 'amneziawg2') return Boolean(features.awg2)
        if (protocol === 'wireguard') return Boolean(features.wireguard || features.amneziawg)
        return Boolean(features[protocol])
      }),
    [features],
  )

  useEffect(() => {
    setSelectedProtocols((prev) => {
      const nextProtocols = prev.filter((protocol) => availableProtocols.includes(protocol))
      if (nextProtocols.length > 0) return nextProtocols
      return availableProtocols.length > 0 ? availableProtocols.slice(0, 1) : []
    })
  }, [availableProtocols])

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)
    try {
      setCodes(await getTgUnlockCodes())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки unlock-кодов')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    if (!isAdmin) return
    void load()
  }, [isAdmin, load])

  const toggleProtocol = (protocol: UnlockCodeProtocol) => {
    setSelectedProtocols((prev) => {
      if (prev.includes(protocol)) {
        return prev.filter((item) => item !== protocol)
      }
      return [...prev, protocol]
    })
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const parsedGrantDays = Number.parseInt(grantDays, 10)
    if (!Number.isFinite(parsedGrantDays) || parsedGrantDays < 1 || parsedGrantDays > 3650) {
      setFeedback({ tone: 'error', text: 'Срок должен быть от 1 до 3650 дней' })
      return
    }
    if (selectedProtocols.length === 0) {
      setFeedback({ tone: 'error', text: 'Выберите хотя бы один протокол' })
      return
    }
    const parsedMaxRedemptions = Number.parseInt(maxRedemptions, 10)
    if (mode === 'multi' && (!Number.isFinite(parsedMaxRedemptions) || parsedMaxRedemptions < 1)) {
      setFeedback({ tone: 'error', text: 'Укажите корректное число активаций' })
      return
    }

    setSaving(true)
    setFeedback(null)
    try {
      const created = await createTgUnlockCode({
        grant_days: parsedGrantDays,
        protocols: selectedProtocols,
        mode,
        max_redemptions: mode === 'single' ? 1 : parsedMaxRedemptions,
        code_expires_at: toEndOfDayIso(codeExpiresAt),
      })
      setCreatedCode(created)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setFeedback({ tone: 'success', text: 'Unlock-код создан' })
      await load({ silent: true })
    } catch (err) {
      setFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Не удалось создать код' })
    } finally {
      setSaving(false)
    }
  }

  const copyCreatedCode = async () => {
    if (!createdCode) return
    try {
      await navigator.clipboard.writeText(createdCode.code)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setFeedback({ tone: 'success', text: 'Код скопирован' })
    } catch {
      setFeedback({ tone: 'error', text: 'Не удалось скопировать код' })
    }
  }

  const handleRevoke = async (code: UnlockCodeRecord) => {
    if (!window.confirm(`Отозвать код «${code.code}»?`)) return
    setRevokingId(code.id)
    setFeedback(null)
    try {
      await revokeTgUnlockCode(code.id)
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
      setFeedback({ tone: 'info', text: `Код «${code.code}» отозван` })
      await load({ silent: true })
    } catch (err) {
      setFeedback({ tone: 'error', text: err instanceof ApiError ? err.message : 'Не удалось отозвать код' })
    } finally {
      setRevokingId(null)
    }
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />
  }

  if (loading) {
    return <UnlockCodesSkeleton />
  }

  return (
    <div className="tg-mini-dashboard space-y-4">
      <MiniPageHeader
        title="Unlock-коды"
        subtitle="Создание ключей продления и отзыв из Telegram"
        onRefresh={() => void load({ silent: true })}
        refreshing={refreshing}
      />

      {error && (
        <div className="tg-mini-inline-alert" role="alert">
          {error}
        </div>
      )}

      {feedback && <FeedbackBanner feedback={feedback} />}

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold">Новый unlock-код</p>
              <p className="text-xs text-muted-foreground">
                Выберите срок, протоколы и режим выдачи для клиента.
              </p>
            </div>
            <Badge variant="secondary" className="shrink-0">
              {codes.length} {codes.length === 1 ? 'код' : codes.length < 5 ? 'кода' : 'кодов'}
            </Badge>
          </div>

          {createdCode && (
            <div className="space-y-3 rounded-xl border bg-muted/20 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">Сгенерированный код</p>
                  <p className="break-all font-mono text-lg font-semibold">{createdCode.code}</p>
                </div>
                <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => void copyCreatedCode()}>
                  <Copy size={14} aria-hidden />
                  Копировать
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">{createdCode.grant_days} дн.</Badge>
                <Badge variant="outline">{createdCode.mode}</Badge>
                <Badge variant="outline">Активаций: {createdCode.max_redemptions}</Badge>
                <Badge variant="outline">Истекает: {formatDateTime(createdCode.code_expires_at)}</Badge>
                {createdCode.protocols.map((protocol) => (
                  <ProtocolPill key={protocol} protocol={protocol as UnlockCodeProtocol} />
                ))}
              </div>
            </div>
          )}

          <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="grant-days">Срок, дни</Label>
                <Input
                  id="grant-days"
                  type="number"
                  min={1}
                  max={3650}
                  value={grantDays}
                  onChange={(event) => setGrantDays(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="code-expires">Срок жизни</Label>
                <Input
                  id="code-expires"
                  type="date"
                  value={codeExpiresAt}
                  onChange={(event) => setCodeExpiresAt(event.target.value)}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Режим</Label>
              <div className="grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant={mode === 'single' ? 'default' : 'outline'}
                  onClick={() => {
                    setMode('single')
                    setMaxRedemptions('1')
                  }}
                >
                  Single
                </Button>
                <Button
                  type="button"
                  variant={mode === 'multi' ? 'default' : 'outline'}
                  onClick={() => {
                    setMode('multi')
                    if (maxRedemptions === '1') setMaxRedemptions('10')
                  }}
                >
                  Multi
                </Button>
              </div>
            </div>

            {mode === 'multi' && (
              <div className="space-y-2">
                <Label htmlFor="max-redemptions">Макс. активаций</Label>
                <Input
                  id="max-redemptions"
                  type="number"
                  min={1}
                  max={1000}
                  value={maxRedemptions}
                  onChange={(event) => setMaxRedemptions(event.target.value)}
                />
              </div>
            )}

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <Label>Протоколы</Label>
                <span className="text-xs text-muted-foreground">{selectedProtocols.length} выбрано</span>
              </div>
              {availableProtocols.length === 0 ? (
                <div className="tg-mini-empty-inline">
                  <CalendarClock size={16} className="text-muted-foreground" aria-hidden />
                  <p className="text-sm text-muted-foreground">Нет доступных протоколов для создания кода</p>
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-3">
                  {availableProtocols.map((protocol) => {
                    const checked = selectedProtocols.includes(protocol)
                    return (
                      <button
                        key={protocol}
                        type="button"
                        onClick={() => toggleProtocol(protocol)}
                        className={cn(
                          'rounded-lg border px-3 py-2 text-left text-sm transition-colors',
                          checked ? 'border-primary bg-primary/10 text-primary' : 'hover:bg-muted/50',
                        )}
                      >
                        <span className="block font-medium">{protocolLabel(protocol)}</span>
                        <span className="text-xs text-muted-foreground">{checked ? 'Выбран' : 'Не выбран'}</span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button type="submit" className="gap-1.5" disabled={saving || availableProtocols.length === 0}>
                {saving ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <KeyRound size={16} aria-hidden />}
                Создать
              </Button>
              <Button type="button" variant="outline" className="gap-1.5" onClick={() => void load({ silent: true })} disabled={refreshing}>
                <RefreshCw size={16} aria-hidden />
                Обновить список
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold">Недавние коды</p>
              <p className="text-xs text-muted-foreground">Показаны последние созданные unlock-коды</p>
            </div>
            <Badge variant="outline" className="shrink-0 gap-1.5">
              <Users size={12} aria-hidden />
              {codes.length}
            </Badge>
          </div>

          {codes.length === 0 ? (
            <div className="tg-mini-filter-empty">
              <KeyRound size={22} className="text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">Пока нет unlock-кодов</p>
              <p className="text-xs text-muted-foreground">Создайте первый код в форме выше</p>
            </div>
          ) : (
            <div className="space-y-2">
              {codes.map((code) => {
                const revoked = Boolean(code.revoked_at)
                const redeemed = unlockCodeRedeemedCount(code)
                const exhausted = isUnlockCodeExhausted(code)
                const statusLabel = unlockCodeStatusLabel(code)
                const redemptions = code.redemptions ?? []
                return (
                  <div
                    key={code.id}
                    className={cn(
                      'flex flex-col gap-3 rounded-xl border bg-card/60 p-3 sm:flex-row sm:items-start sm:justify-between',
                      exhausted && !revoked && 'border-amber-500/30 bg-amber-500/5',
                      revoked && 'opacity-70',
                    )}
                  >
                    <div className="min-w-0 space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="break-all font-mono text-sm font-semibold">{code.code}</p>
                        <Badge variant={code.mode === 'multi' ? 'default' : 'secondary'}>{code.mode}</Badge>
                        {statusLabel === 'Отозван' && <Badge variant="destructive">Отозван</Badge>}
                        {statusLabel === 'Активирован' && <Badge variant="success">Активирован</Badge>}
                        {statusLabel === 'Исчерпан' && <Badge variant="warning">Исчерпан</Badge>}
                        {statusLabel === 'Частично' && <Badge variant="outline">Частично</Badge>}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {code.grant_days} дн. · активаций {redeemed} / {code.max_redemptions}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Протоколы:{' '}
                        {code.protocols
                          .map((protocol) => protocolLabel(protocol as UnlockCodeProtocol))
                          .join(', ') || '—'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Создан: {formatDateTime(code.created_at)} · Истекает:{' '}
                        {formatDateTime(code.code_expires_at)}
                      </p>
                      {redemptions.length > 0 && (
                        <div className="space-y-1 pt-1">
                          <p className="text-xs font-medium text-foreground">Активации</p>
                          {redemptions.map((item) => (
                            <p key={item.id} className="text-xs text-muted-foreground">
                              {item.client_name}
                              {item.node_name ? ` · ${item.node_name}` : ''}
                              {item.redeemed_at ? ` · ${formatDateTime(item.redeemed_at)}` : ''}
                            </p>
                          ))}
                        </div>
                      )}
                      {code.revoked_at && (
                        <p className="text-xs text-muted-foreground">Отозван: {formatDateTime(code.revoked_at)}</p>
                      )}
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="gap-1.5"
                        disabled={revoked || revokingId === code.id}
                        onClick={() => void handleRevoke(code)}
                      >
                        {revokingId === code.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                        Отозвать
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
