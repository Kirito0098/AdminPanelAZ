import { useEffect, useMemo, useState } from 'react'
import { Download, Loader2, RotateCcw, Smartphone } from 'lucide-react'
import { ApiError } from '@/api/client'
import { getPortalAppLinks, updatePortalAppLinks } from '@/api/portal'
import {
  PORTAL_APP_PROTOCOLS,
  PORTAL_OS_OPTIONS,
  type PortalAppLinks,
} from '@/lib/portalAppDownloads'
import {
  SettingsCard as Card,
  SettingsCardContent as CardContent,
  SettingsCardDescription as CardDescription,
  SettingsCardHeader as CardHeader,
  SettingsCardTitle as CardTitle,
} from '@/components/settings/SettingsCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'

/** Короткая подпись по умолчанию — полный адрес уходит в title. */
function shortUrl(url: string): string {
  return url.replace(/^https?:\/\//, '').replace(/\/$/, '')
}

export default function PortalAppLinksCard() {
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
  const [links, setLinks] = useState<PortalAppLinks>({})
  const [saved, setSaved] = useState<PortalAppLinks>({})
  const [defaults, setDefaults] = useState<PortalAppLinks>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    getPortalAppLinks()
      .then((data) => {
        setLinks(data.links ?? {})
        setSaved(data.links ?? {})
        setDefaults(data.defaults ?? {})
      })
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки ссылок'))
      .finally(() => setLoading(false))
  }, [notifyError])

  const dirty = useMemo(() => JSON.stringify(links) !== JSON.stringify(saved), [links, saved])

  const setCell = (protocol: string, platform: string, value: string) => {
    setLinks((prev) => {
      const next: PortalAppLinks = { ...prev, [protocol]: { ...(prev[protocol] ?? {}) } }
      const trimmed = value.trim()
      if (trimmed) next[protocol][platform as keyof PortalAppLinks[string]] = trimmed
      else delete next[protocol][platform as keyof PortalAppLinks[string]]
      if (Object.keys(next[protocol]).length === 0) delete next[protocol]
      return next
    })
  }

  const resetProtocol = (protocol: string) => {
    setLinks((prev) => {
      const next = { ...prev }
      delete next[protocol]
      return next
    })
  }

  const save = async () => {
    setSaving(true)
    try {
      const data = await updatePortalAppLinks(links)
      setLinks(data.links ?? {})
      setSaved(data.links ?? {})
      setDefaults(data.defaults ?? {})
      if (data.warnings?.length) {
        notifyWarning(`Часть ссылок не сохранена: ${data.warnings.join('; ')}`)
      } else {
        success('Ссылки на приложения сохранены — портал уже отдаёт новые адреса')
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Smartphone size={16} aria-hidden />
          </span>
          Ссылки на приложения
        </CardTitle>
        <CardDescription>
          Куда ведут кнопки «Скачать приложение» в клиентском портале. Пустое поле — официальная
          ссылка проекта, такие значения в базу не пишутся.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 size={16} className="animate-spin" /> Загрузка…
          </p>
        ) : (
          <>
            {PORTAL_APP_PROTOCOLS.map((protocol) => {
              const hasOverrides = Object.keys(links[protocol.id] ?? {}).length > 0
              return (
                <div key={protocol.id} className="space-y-2 rounded-lg border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{protocol.label}</p>
                      <p className="text-xs text-muted-foreground">{protocol.hint}</p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="gap-1.5"
                      disabled={!hasOverrides}
                      onClick={() => resetProtocol(protocol.id)}
                    >
                      <RotateCcw size={13} />
                      Сбросить
                    </Button>
                  </div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
                    {PORTAL_OS_OPTIONS.map((os) => {
                      const fallback = defaults[protocol.id]?.[os.id] ?? ''
                      const value = links[protocol.id]?.[os.id] ?? ''
                      const id = `portal-app-${protocol.id}-${os.id}`
                      return (
                        <div key={os.id} className="space-y-1">
                          <Label htmlFor={id} className="text-[11px] text-muted-foreground">
                            {os.label}
                          </Label>
                          <Input
                            id={id}
                            value={value}
                            onChange={(e) => setCell(protocol.id, os.id, e.target.value)}
                            placeholder={fallback ? shortUrl(fallback) : 'https://…'}
                            title={fallback ? `По умолчанию: ${fallback}` : undefined}
                            inputMode="url"
                            autoComplete="off"
                            spellCheck={false}
                            className="h-9 font-mono text-xs"
                          />
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}

            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Download size={13} aria-hidden />
                Изменения применяются сразу, перезапуск панели не нужен
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!dirty || saving}
                  onClick={() => setLinks(saved)}
                >
                  Отменить
                </Button>
                <Button type="button" size="sm" disabled={!dirty || saving} onClick={() => void save()}>
                  {saving ? 'Сохранение…' : 'Сохранить'}
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
