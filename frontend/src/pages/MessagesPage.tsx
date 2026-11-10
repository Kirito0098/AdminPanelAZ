import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronLeft, MessageSquare } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { ApiError } from '@/api/client'
import { getMessageThreads, markMessagesRead } from '@/api/messages'
import ChatThread from '@/components/messages/ChatThread'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatDate } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { MessageThread } from '@/types'

/** Раздел «Сообщения»: список диалогов и лента выбранного (на узких экранах — по очереди). */
export default function MessagesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = Number.parseInt(searchParams.get('user') ?? '', 10)
  const hasSelected = Number.isFinite(selectedId) && selectedId > 0
  const [threads, setThreads] = useState<MessageThread[]>([])
  const [search, setSearch] = useState('')
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      setThreads(await getMessageThreads({ q: search.trim() || undefined, unread: unreadOnly }))
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось загрузить диалоги')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [search, unreadOnly])

  useEffect(() => {
    void load()
  }, [load])

  // Список диалогов освежаем раз в 30 с (тихо, только на видимой вкладке).
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!document.hidden) void load(true)
    }, 30_000)
    return () => window.clearInterval(timer)
  }, [load])

  const selected = useMemo(
    () => threads.find((thread) => thread.user_id === selectedId) ?? null,
    [threads, selectedId],
  )

  const openThread = (userId: number | null) => {
    const next = new URLSearchParams(searchParams)
    if (userId === null) next.delete('user')
    else next.set('user', String(userId))
    setSearchParams(next, { replace: true })
  }

  const afterChange = () => {
    if (hasSelected) void markMessagesRead(selectedId)
    void load()
  }

  return (
    <div className="flex h-[calc(100dvh-9rem)] min-h-[24rem] flex-col gap-3">
      <PageSectionHeader
        card
        icon={MessageSquare}
        title="Сообщения"
        description="Личные сообщения администраторов и абонентов."
      />

      <div className="flex min-h-0 flex-1 gap-3">
        <aside
          className={cn(
            'w-full max-w-xs flex-col gap-2 md:flex',
            hasSelected ? 'hidden md:flex' : 'flex',
          )}
        >
          <div className="flex items-center gap-2">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск по логину"
              aria-label="Поиск по логину"
            />
            <Button
              type="button"
              size="sm"
              variant={unreadOnly ? 'default' : 'outline'}
              onClick={() => setUnreadOnly((prev) => !prev)}
            >
              Непрочитанные
            </Button>
          </div>
          <div className="min-h-0 flex-1 space-y-1 overflow-y-auto rounded-lg border p-1">
            {loading && <p className="p-2 text-xs text-muted-foreground">Загрузка…</p>}
            {!loading && threads.length === 0 && (
              <p className="p-2 text-xs text-muted-foreground">Диалогов пока нет.</p>
            )}
            {threads.map((thread) => (
              <button
                key={thread.user_id}
                type="button"
                onClick={() => openThread(thread.user_id)}
                className={cn(
                  'flex w-full flex-col gap-0.5 rounded-lg px-2 py-2 text-left hover:bg-muted/60',
                  thread.user_id === selectedId && 'bg-muted',
                )}
              >
                <span className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">{thread.username}</span>
                  {thread.unread_count > 0 && (
                    <Badge variant="destructive" className="text-[10px]">
                      {thread.unread_count > 9 ? '9+' : thread.unread_count}
                    </Badge>
                  )}
                  <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                    {formatDate(thread.last_at)}
                  </span>
                </span>
                <span className="truncate text-xs text-muted-foreground">
                  {thread.last_direction === 'out' ? 'Вы: ' : ''}
                  {thread.last_text}
                </span>
              </button>
            ))}
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </aside>

        <section
          className={cn(
            'min-h-0 flex-1 flex-col gap-2 md:flex',
            hasSelected ? 'flex' : 'hidden md:flex',
          )}
        >
          {selected ? (
            <>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="md:hidden"
                  onClick={() => openThread(null)}
                  aria-label="Назад к списку диалогов"
                >
                  <ChevronLeft size={16} />
                </Button>
                <MessageSquare size={16} aria-hidden />
                <span className="text-sm font-medium">{selected.username}</span>
              </div>
              <ChatThread userId={selected.user_id} onSent={afterChange} onRead={() => void load()} />
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-lg border">
              <EmptyState
                icon={MessageSquare}
                title="Выберите диалог"
                description="Откройте диалог из списка слева, чтобы прочитать сообщения."
              />
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
