import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bot, Globe, RefreshCw, RotateCcw, Save } from 'lucide-react'
import {
  getWarperDomains,
  saveWarperUserDomainsText,
  setWarperDomainList,
} from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { WarperHealthResponse } from '@/types'
import { buildUserDomainsTextFromItems, countActiveTextLines, isWarperDisabled } from './utils'

const BUILTIN_LISTS = {
  gemini: { title: 'Google Gemini', description: 'Домены сервисов Gemini' },
  chatgpt: { title: 'ChatGPT', description: 'Домены OpenAI и ChatGPT' },
} as const

interface DomainsTabProps {
  health: WarperHealthResponse | null
  onDomainsChange?: (count: number) => void
}

export default function DomainsTab({ health, onDomainsChange }: DomainsTabProps) {
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const disabled = isWarperDisabled(health)

  const [savedText, setSavedText] = useState('')
  const [draftText, setDraftText] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [listBusy, setListBusy] = useState<string | null>(null)
  const [listStatus, setListStatus] = useState({ gemini: false, chatgpt: false })

  const dirty = draftText !== savedText
  const domainCount = useMemo(() => countActiveTextLines(draftText), [draftText])

  const load = useCallback(async () => {
    if (!health?.installed) {
      setSavedText('')
      setDraftText('')
      setLoading(false)
      setLoadError(null)
      onDomainsChange?.(0)
      return
    }
    setLoading(true)
    setLoadError(null)
    try {
      const listsData = await getWarperDomains()
      const content =
        listsData.user_text?.trim() ||
        buildUserDomainsTextFromItems(listsData.domains ?? [])
      setSavedText(content)
      setDraftText(content)
      setListStatus({
        gemini: listsData.lists?.gemini ?? false,
        chatgpt: listsData.lists?.chatgpt ?? false,
      })
      onDomainsChange?.(countActiveTextLines(content))
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Не удалось загрузить домены')
    } finally {
      setLoading(false)
    }
  }, [health?.installed, onDomainsChange])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id, health?.installed])

  async function handleSave() {
    if (!dirty) return
    setSaving(true)
    try {
      const result = await saveWarperUserDomainsText(draftText)
      setSavedText(draftText)
      onDomainsChange?.(countActiveTextLines(draftText))
      success(result.message ?? 'Домены сохранены')
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось сохранить домены')
    } finally {
      setSaving(false)
    }
  }

  async function setListEnabled(name: 'gemini' | 'chatgpt', enable: boolean) {
    if (listStatus[name] === enable) return
    setListBusy(name)
    try {
      await setWarperDomainList(name, enable)
      const label = BUILTIN_LISTS[name].title
      success(`${label} ${enable ? 'включён' : 'выключен'}`)
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : `Не удалось изменить список ${name}`)
    } finally {
      setListBusy(null)
    }
  }

  if (loading && !savedText) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {loadError && <EmptyState title="Ошибка загрузки" description={loadError} />}

      <StatusPanel title="Встроенные списки" icon={Bot}>
        <p className="mb-3 text-sm text-muted-foreground">
          Готовые наборы доменов. Включаются отдельно от пользовательского списка ниже.
        </p>
        <div className="divide-y rounded-lg border">
          {(Object.keys(BUILTIN_LISTS) as Array<keyof typeof BUILTIN_LISTS>).map((name) => {
            const enabled = listStatus[name]
            const busy = listBusy === name
            const meta = BUILTIN_LISTS[name]
            const switchDisabled = disabled || (listBusy !== null && !busy)
            return (
              <div
                key={name}
                className={`flex items-center justify-between gap-4 p-4 transition-colors ${
                  switchDisabled ? 'opacity-70' : 'hover:bg-muted/30'
                }`}
              >
                <div className="min-w-0">
                  <div className="font-medium">{meta.title}</div>
                  <div className="text-sm text-muted-foreground">{meta.description}</div>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="w-14 text-right text-sm tabular-nums text-muted-foreground">
                    {busy ? '…' : enabled ? 'Вкл' : 'Выкл'}
                  </span>
                  <Switch
                    checked={enabled}
                    disabled={switchDisabled}
                    aria-label={`${meta.title}: ${enabled ? 'включён' : 'выключен'}`}
                    onCheckedChange={(checked) => void setListEnabled(name, checked)}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </StatusPanel>

      <StatusPanel title="Пользовательские домены" icon={Globe}>
        <p className="mb-4 text-sm text-muted-foreground">
          Текстовый файл доменов с комментариями. Сохранение выполняет валидацию и одну синхронизацию с
          kresd — без добавления по одному домену.
        </p>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Badge variant="secondary">Доменов: {domainCount}</Badge>
          {dirty && <Badge variant="warning">Есть несохранённые изменения</Badge>}
          {disabled && <Badge variant="warning">Только просмотр</Badge>}
        </div>

        <Textarea
          value={draftText}
          onChange={(e) => setDraftText(e.target.value)}
          disabled={disabled || saving}
          spellCheck={false}
          className="min-h-[20rem] resize-y font-mono text-xs leading-relaxed"
          placeholder={'# Пользовательские домены:\nexample.com\n*.cdn.example.com'}
        />

        <div className="mt-4 flex flex-wrap gap-2">
          <Button disabled={disabled || saving || !dirty} onClick={() => void handleSave()}>
            <Save className="mr-1.5 h-4 w-4" />
            {saving ? 'Сохранение…' : 'Сохранить'}
          </Button>
          <Button
            variant="outline"
            disabled={disabled || saving || !dirty}
            onClick={() => setDraftText(savedText)}
          >
            <RotateCcw className="mr-1.5 h-4 w-4" />
            Сбросить
          </Button>
          <Button variant="secondary" size="sm" disabled={loading || saving} onClick={() => void load()}>
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Обновить
          </Button>
        </div>
      </StatusPanel>
    </div>
  )
}
