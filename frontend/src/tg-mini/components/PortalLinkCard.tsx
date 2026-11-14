import { useCallback, useEffect, useState } from 'react'
import { Copy, ExternalLink, Link2, Loader2, RefreshCw } from 'lucide-react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import { createTgPortalLink, getTgPortalLink, rotateTgPortalLink } from '@/tg-mini/api'
import { formatDateTime } from '@/lib/datetime'
import { openExternalLink } from '@/tg-mini/lib/shareDownloadLink'
import type { TgPortalLink } from '@/types'

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Не удалось получить ссылку портала'
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/** Ссылка клиентского портала для самого абонента: получить, скопировать, перевыпустить. */
export default function PortalLinkCard() {
  const { features, featuresReady } = useTgAuth()
  const [link, setLink] = useState<TgPortalLink | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<'create' | 'rotate' | 'copy' | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const enabled = Boolean(features.client_portal)

  useEffect(() => {
    if (!featuresReady || !enabled) {
      setLoading(false)
      return
    }
    let alive = true
    setLoading(true)
    void getTgPortalLink()
      .then((data) => {
        if (alive) setLink(data)
      })
      .catch((err) => {
        if (alive) setError(errorText(err))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [enabled, featuresReady])

  const applyLink = useCallback(async (next: TgPortalLink, message: string) => {
    setLink(next)
    setConfirming(false)
    if (next.url) {
      const copied = await copyText(next.url)
      setNotice(copied ? message : 'Ссылка готова — скопируйте её вручную')
    }
  }, [])

  const create = useCallback(async () => {
    setBusy('create')
    setError(null)
    try {
      const next = await createTgPortalLink()
      await applyLink(next, 'Ссылка создана и скопирована')
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(null)
    }
  }, [applyLink])

  const rotate = useCallback(async () => {
    setBusy('rotate')
    setError(null)
    try {
      const next = await rotateTgPortalLink()
      await applyLink(next, 'Ссылка перевыпущена и скопирована')
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(null)
    }
  }, [applyLink])

  const copy = useCallback(async () => {
    if (!link?.url) return
    setBusy('copy')
    const copied = await copyText(link.url)
    setNotice(copied ? 'Скопировано' : 'Браузер не дал доступ к буферу обмена')
    setBusy(null)
  }, [link])

  if (!featuresReady || !enabled) return null

  const expired = Boolean(link?.expired)
  const hasLink = Boolean(link?.exists && link.url && !expired)

  return (
    <Card>
      <CardContent className="space-y-3 p-3">
        <div className="flex items-center gap-2">
          <Link2 size={18} className="shrink-0 text-primary" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Клиентский портал</p>
            <p className="text-xs text-muted-foreground">
              Одна ссылка со всеми вашими профилями — откройте на устройстве без входа в панель.
            </p>
          </div>
        </div>

        {loading ? (
          <p className="text-xs text-muted-foreground">Загрузка ссылки…</p>
        ) : error ? (
          <p className="text-xs text-destructive">{error}</p>
        ) : hasLink && link?.url ? (
          <div className="space-y-1">
            <p className="break-all rounded-lg border bg-muted/20 px-2 py-1.5 font-mono text-[11px]">
              {link.url}
            </p>
            <p className="text-xs text-muted-foreground">
              {link.expires_at
                ? `Действует до ${formatDateTime(link.expires_at)}`
                : 'Срок действия не ограничен'}
            </p>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            {expired
              ? 'Срок действия ссылки истёк — получите новую.'
              : 'Ссылка ещё не создана. Получите её и отправьте себе.'}
          </p>
        )}

        {notice && <p className="text-xs text-muted-foreground">{notice}</p>}

        <div className="flex flex-wrap gap-2">
          {!hasLink ? (
            <Button type="button" size="sm" onClick={() => void create()} disabled={busy !== null}>
              {busy === 'create' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Link2 size={14} />
              )}
              {expired ? 'Получить новую' : 'Получить ссылку'}
            </Button>
          ) : (
            <>
              <Button type="button" size="sm" onClick={() => void copy()} disabled={busy !== null}>
                {busy === 'copy' ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Copy size={14} />
                )}
                Скопировать
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => link?.url && openExternalLink(link.url)}
              >
                <ExternalLink size={14} />
                Открыть
              </Button>
              {confirming ? (
                <>
                  <Button
                    type="button"
                    size="sm"
                    variant="destructive"
                    onClick={() => void rotate()}
                    disabled={busy !== null}
                  >
                    {busy === 'rotate' ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : null}
                    Точно
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirming(false)}
                    disabled={busy !== null}
                  >
                    Отмена
                  </Button>
                </>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setConfirming(true)}
                  disabled={busy !== null}
                >
                  <RefreshCw size={14} />
                  Перевыпустить
                </Button>
              )}
            </>
          )}
        </div>

        {confirming && (
          <p className="text-xs text-muted-foreground">
            Перевыпуск отзовёт текущую ссылку — старая перестанет открываться.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
