import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeft, Loader2, MessagesSquare, Search } from 'lucide-react'
import { ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useIntervalWhenVisible } from '@/hooks/useIntervalWhenVisible'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import {
  getTgMeMessages,
  getTgMessageThread,
  getTgMessageThreads,
  markTgMeMessagesRead,
  sendTgMeMessage,
  sendTgMessageThread,
} from '@/tg-mini/api'
import { formatRelative, formatTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { MessageThread, UserMessageItem } from '@/types'

const MESSAGE_LIMIT = 4096
const FEED_LIMIT = 50
const POLL_MS = 7_000

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback
}

/** Лента приходит по возрастанию id (новые в конце) — сравниваем хвост, чтобы не дёргать DOM зря. */
function sameFeed(prev: UserMessageItem[], next: UserMessageItem[]): boolean {
  return (
    prev.length === next.length &&
    prev[prev.length - 1]?.id === next[next.length - 1]?.id
  )
}

interface ChatFeedProps {
  messages: UserMessageItem[]
  /** Направление собственных сообщений: у абонента 'in', у админа 'out'. */
  ownDirection: 'in' | 'out'
  loading: boolean
  sending: boolean
  draft: string
  onDraftChange: (value: string) => void
  onSubmit: () => void
  placeholder: string
  emptyTitle: string
  emptyText: string
  error?: string | null
  warning?: string | null
}

function ChatFeed({
  messages,
  ownDirection,
  loading,
  sending,
  draft,
  onDraftChange,
  onSubmit,
  placeholder,
  emptyTitle,
  emptyText,
  error,
  warning,
}: ChatFeedProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length])

  return (
    <div className="tg-mini-chat">
      <div className="tg-mini-chat-feed" aria-live="polite">
        {loading && messages.length === 0 ? (
          <p className="tg-mini-chat-note">Загрузка…</p>
        ) : messages.length === 0 ? (
          <div className="tg-mini-chat-empty">
            <MessagesSquare size={22} className="text-muted-foreground" aria-hidden />
            <p className="text-sm font-medium">{emptyTitle}</p>
            <p className="text-xs text-muted-foreground">{emptyText}</p>
          </div>
        ) : (
          messages.map((message) => {
            const own = message.direction === ownDirection
            return (
              <div key={message.id} className={cn('tg-mini-chat-row', own && 'is-own')}>
                <div className={cn('tg-mini-chat-bubble', own && 'is-own')}>
                  <p className="tg-mini-chat-text">{message.text}</p>
                  <p className="tg-mini-chat-time">{formatTime(message.created_at)}</p>
                </div>
              </div>
            )
          })
        )}
        <div ref={bottomRef} />
      </div>

      {warning && <p className="text-xs text-amber-600 dark:text-amber-400">{warning}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}

      <form
        className="tg-mini-chat-composer"
        onSubmit={(event) => {
          event.preventDefault()
          onSubmit()
        }}
      >
        <textarea
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              onSubmit()
            }
          }}
          maxLength={MESSAGE_LIMIT}
          rows={2}
          placeholder={placeholder}
          aria-label={placeholder}
          className="tg-mini-chat-input"
        />
        <Button type="submit" size="sm" className="shrink-0" disabled={sending || !draft.trim()}>
          {sending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : 'Отправить'}
        </Button>
      </form>
    </div>
  )
}

/** Абонент: свой диалог с администратором. */
function SubscriberChat() {
  const [messages, setMessages] = useState<UserMessageItem[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const markRead = useCallback(() => {
    void markTgMeMessagesRead().catch(() => {
      // Счётчик непрочитанных не критичен — следующая загрузка повторит.
    })
  }, [])

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true)
      try {
        const next = await getTgMeMessages({ limit: FEED_LIMIT })
        setMessages((prev) => (sameFeed(prev, next) ? prev : next))
        setError(null)
        markRead()
      } catch (err) {
        if (!silent) setError(errorText(err, 'Не удалось загрузить переписку'))
      } finally {
        if (!silent) setLoading(false)
      }
    },
    [markRead],
  )

  useEffect(() => {
    void load()
  }, [load])

  useIntervalWhenVisible(() => void load(true), POLL_MS, {
    onBecomeVisible: () => void load(true),
  })

  const refresh = async () => {
    setRefreshing(true)
    try {
      await load()
    } finally {
      setRefreshing(false)
    }
  }

  const submit = async () => {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    setError(null)
    try {
      await sendTgMeMessage(text)
      setDraft('')
      await load()
    } catch (err) {
      setError(errorText(err, 'Не удалось отправить сообщение'))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="tg-mini-dashboard space-y-3">
      <MiniPageHeader
        title="Чат"
        subtitle="Переписка с администратором"
        onRefresh={() => void refresh()}
        refreshing={refreshing}
      />
      <ChatFeed
        messages={messages}
        ownDirection="in"
        loading={loading}
        sending={sending}
        draft={draft}
        onDraftChange={setDraft}
        onSubmit={() => void submit()}
        placeholder="Сообщение администратору…"
        emptyTitle="Сообщений пока нет"
        emptyText="Напишите администратору — ответ придёт сюда"
        error={error}
      />
    </div>
  )
}

interface AdminThreadFeedProps {
  thread: MessageThread
  onActivity: () => void
}

/** Админ: лента выбранного абонента и ответ ему. */
function AdminThreadFeed({ thread, onActivity }: AdminThreadFeedProps) {
  const [messages, setMessages] = useState<UserMessageItem[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

  // Колбэк в ref: его identity не должна перезапускать загрузку (иначе цикл «лента → список → лента»).
  const onActivityRef = useRef(onActivity)
  useEffect(() => {
    onActivityRef.current = onActivity
  }, [onActivity])

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true)
      try {
        const next = await getTgMessageThread(thread.user_id, { limit: FEED_LIMIT })
        setMessages((prev) => (sameFeed(prev, next) ? prev : next))
        setError(null)
        // Открытие диалога помечает входящие прочитанными на сервере — обновляем список.
        if (!silent) onActivityRef.current()
      } catch (err) {
        if (!silent) setError(errorText(err, 'Не удалось загрузить переписку'))
      } finally {
        if (!silent) setLoading(false)
      }
    },
    [thread.user_id],
  )

  useEffect(() => {
    void load()
  }, [load])

  useIntervalWhenVisible(() => void load(true), POLL_MS)

  const submit = async () => {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    setError(null)
    setWarning(null)
    try {
      const result = await sendTgMessageThread(thread.user_id, text)
      setDraft('')
      if (!result.delivered) {
        setWarning(result.warning ?? 'Сообщение сохранено, но не доставлено в Telegram')
      }
      await load(true)
      onActivityRef.current()
    } catch (err) {
      setError(errorText(err, 'Не удалось отправить сообщение'))
    } finally {
      setSending(false)
    }
  }

  return (
    <ChatFeed
      messages={messages}
      ownDirection="out"
      loading={loading}
      sending={sending}
      draft={draft}
      onDraftChange={setDraft}
      onSubmit={() => void submit()}
      placeholder="Ответ абоненту…"
      emptyTitle="Сообщений пока нет"
      emptyText="Ответ появится в диалоге и уйдёт абоненту в Telegram"
      error={error}
      warning={warning}
    />
  )
}

/** Админ: список диалогов и лента выбранного абонента. */
function AdminChat() {
  const [threads, setThreads] = useState<MessageThread[]>([])
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<MessageThread | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [search])

  const loadThreads = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true)
      try {
        const data = await getTgMessageThreads({ q: query || undefined })
        setThreads(data)
        setError(null)
      } catch (err) {
        if (!silent) setError(errorText(err, 'Не удалось загрузить диалоги'))
      } finally {
        if (!silent) setLoading(false)
      }
    },
    [query],
  )

  useEffect(() => {
    void loadThreads()
  }, [loadThreads])

  // Пока открыт диалог, список не опрашиваем: лента сама обновляет его после чтения/отправки.
  useIntervalWhenVisible(() => void loadThreads(true), POLL_MS, {
    enabled: selected == null,
    onBecomeVisible: () => {
      if (selected == null) void loadThreads(true)
    },
  })

  const refreshThreads = useCallback(() => {
    void loadThreads(true)
  }, [loadThreads])

  const refresh = async () => {
    setRefreshing(true)
    try {
      await loadThreads()
    } finally {
      setRefreshing(false)
    }
  }

  if (selected) {
    return (
      <div className="tg-mini-dashboard space-y-3">
        <div className="tg-mini-chat-head">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1 px-2"
            onClick={() => {
              setSelected(null)
              refreshThreads()
            }}
            aria-label="Назад к списку диалогов"
          >
            <ChevronLeft size={16} aria-hidden />
            Назад
          </Button>
          <span className="truncate text-sm font-medium">{selected.username}</span>
        </div>
        <AdminThreadFeed key={selected.user_id} thread={selected} onActivity={refreshThreads} />
      </div>
    )
  }

  return (
    <div className="tg-mini-dashboard space-y-3">
      <MiniPageHeader
        title="Чат"
        subtitle={`${threads.length} диалог${threads.length === 1 ? '' : 'ов'}`}
        onRefresh={() => void refresh()}
        refreshing={refreshing}
      />

      <div className="tg-mini-search-wrap">
        <Search size={15} className="tg-mini-search-icon" aria-hidden />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Поиск по логину…"
          className="tg-mini-search-input"
          aria-label="Поиск диалогов"
        />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading && threads.length === 0 ? (
        <div className="tg-mini-skeleton tg-mini-skeleton-section" aria-busy="true" />
      ) : threads.length === 0 ? (
        <div className="tg-mini-filter-empty">
          <MessagesSquare size={22} className="text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">{query ? 'Ничего не найдено' : 'Нет диалогов'}</p>
          <p className="text-xs text-muted-foreground">
            {query ? 'Измените запрос поиска' : 'Сообщения абонентов появятся здесь'}
          </p>
        </div>
      ) : (
        threads.map((thread) => (
          <Card key={thread.user_id} className="tg-mini-config-card">
            <CardContent className="p-0">
              <button
                type="button"
                className="tg-mini-chat-thread"
                onClick={() => setSelected(thread)}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">{thread.username}</span>
                    {thread.unread_count > 0 && (
                      <Badge variant="destructive" className="text-[10px]">
                        {thread.unread_count > 9 ? '9+' : thread.unread_count}
                      </Badge>
                    )}
                    <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                      {formatRelative(thread.last_at)}
                    </span>
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {thread.last_direction === 'out' ? 'Вы: ' : ''}
                    {thread.last_text}
                  </p>
                </div>
              </button>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  )
}

export default function Messages() {
  const { isAdmin } = useTgAuth()
  return isAdmin ? <AdminChat /> : <SubscriberChat />
}
