import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import { getUserMessages, markMessagesRead, sendUserMessage } from '@/api/messages'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatDate } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { UserMessageItem } from '@/types'

interface ChatThreadProps {
  userId: number
  onSent?: () => void
  onRead?: () => void
}

/** Лента диалога с абонентом: история и поле ответа (Enter — отправить). */
export default function ChatThread({ userId, onSent, onRead }: ChatThreadProps) {
  const [messages, setMessages] = useState<UserMessageItem[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [warning, setWarning] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // Колбэки держим в ref: иначе inline-пропсы меняют identity `load` и запускают
  // бесконечный цикл «загрузка → markRead → onRead → ре-рендер → загрузка».
  const onReadRef = useRef(onRead)
  const onSentRef = useRef(onSent)
  useEffect(() => {
    onReadRef.current = onRead
    onSentRef.current = onSent
  }, [onRead, onSent])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setMessages(await getUserMessages(userId, { limit: 100 }))
      await markMessagesRead(userId)
      onReadRef.current?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось загрузить переписку')
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length])

  const submit = async () => {
    const text = draft.trim()
    if (!text || busy) return
    setBusy(true)
    setError(null)
    setWarning(null)
    try {
      const result = await sendUserMessage(userId, text)
      setMessages((prev) => [...prev, result.message])
      setDraft('')
      if (!result.delivered) setWarning(result.warning ?? 'Сообщение не доставлено')
      onSentRef.current?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить сообщение')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="min-h-[12rem] flex-1 space-y-2 overflow-y-auto rounded-lg border bg-muted/20 p-3">
        {loading && <p className="text-xs text-muted-foreground">Загрузка…</p>}
        {!loading && messages.length === 0 && (
          <p className="text-xs text-muted-foreground">Сообщений пока нет.</p>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={cn('flex', message.direction === 'out' ? 'justify-end' : 'justify-start')}
          >
            <div
              className={cn(
                'max-w-[80%] rounded-lg border px-3 py-2 text-sm',
                message.direction === 'out'
                  ? 'border-primary/30 bg-primary text-primary-foreground'
                  : 'bg-background',
              )}
            >
              <p className="whitespace-pre-wrap break-words">{message.text}</p>
              <p className="mt-1 text-[10px] opacity-70">{formatDate(message.created_at)}</p>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {warning && <p className="text-xs text-amber-600">{warning}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex items-center gap-2">
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void submit()
            }
          }}
          placeholder="Ответ абоненту…"
          maxLength={4096}
          aria-label="Ответ абоненту"
        />
        <Button type="button" onClick={() => void submit()} disabled={busy || !draft.trim()}>
          {busy ? 'Отправка…' : 'Отправить'}
        </Button>
      </div>
    </div>
  )
}
