import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bot, Plus, RefreshCw, Search, Trash2, Upload } from 'lucide-react'
import {
  addWarperDomain,
  addWarperDomainsBulk,
  getWarperDomains,
  removeWarperDomain,
  setWarperDomainList,
  syncWarperDomains,
} from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { WarperDomainItem, WarperHealthResponse } from '@/types'
import { isWarperDisabled, parseBulkLines } from './utils'

function domainLabel(item: WarperDomainItem | string): string {
  if (typeof item === 'string') return item
  return item.domain ?? item.name ?? ''
}

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

  const [domains, setDomains] = useState<WarperDomainItem[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [newDomain, setNewDomain] = useState('')
  const [bulkText, setBulkText] = useState('')
  const [showBulk, setShowBulk] = useState(false)
  const [adding, setAdding] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [listBusy, setListBusy] = useState<string | null>(null)
  const [listStatus, setListStatus] = useState({ gemini: false, chatgpt: false })
  const [removeTarget, setRemoveTarget] = useState<string | null>(null)
  const [removing, setRemoving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await getWarperDomains()
      const items = data.domains ?? []
      setDomains(items)
      setListStatus({
        gemini: data.lists?.gemini ?? false,
        chatgpt: data.lists?.chatgpt ?? false,
      })
      onDomainsChange?.(items.length)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Не удалось загрузить домены')
    } finally {
      setLoading(false)
    }
  }, [onDomainsChange])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return domains
    return domains.filter((item) => domainLabel(item).toLowerCase().includes(q))
  }, [domains, search])

  async function handleAdd() {
    const value = newDomain.trim()
    if (!value) return
    setAdding(true)
    try {
      await addWarperDomain(value)
      success(`Домен ${value} добавлен`)
      setNewDomain('')
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось добавить домен')
    } finally {
      setAdding(false)
    }
  }

  async function handleBulkAdd() {
    const items = parseBulkLines(bulkText)
    if (items.length === 0) return
    setAdding(true)
    try {
      const result = await addWarperDomainsBulk(items)
      success(`Добавлено доменов: ${result.added_count}`)
      if (result.errors?.length) {
        notifyError(`Ошибок: ${result.errors.length}`)
      }
      setBulkText('')
      setShowBulk(false)
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось импортировать домены')
    } finally {
      setAdding(false)
    }
  }

  async function handleSync() {
    setSyncing(true)
    try {
      await syncWarperDomains()
      success('Домены синхронизированы. OVPN — переподключение; WG/AWG — обновите конфиг.')
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось синхронизировать домены')
    } finally {
      setSyncing(false)
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

  async function confirmRemove() {
    if (!removeTarget) return
    setRemoving(true)
    try {
      await removeWarperDomain(removeTarget)
      success(`Домен ${removeTarget} удалён`)
      setRemoveTarget(null)
      await load()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось удалить домен')
    } finally {
      setRemoving(false)
    }
  }

  if (loading && domains.length === 0) {
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
          Готовые наборы доменов. После включения нажмите «Синхронизировать», если домены не появились
          сразу.
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

      <StatusPanel title="Домены" icon={Search}>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Badge variant="secondary">Доменов: {domains.length}</Badge>
          {search && <Badge variant="outline">Найдено: {filtered.length}</Badge>}
        </div>

        <div className="mb-4 flex flex-col gap-2 sm:flex-row">
          <Input
            placeholder="example.com"
            value={newDomain}
            onChange={(e) => setNewDomain(e.target.value)}
            disabled={disabled || adding}
            onKeyDown={(e) => e.key === 'Enter' && void handleAdd()}
          />
          <Button disabled={disabled || adding || !newDomain.trim()} onClick={() => void handleAdd()}>
            <Plus className="mr-1.5 h-4 w-4" />
            Добавить
          </Button>
          <Button variant="outline" disabled={disabled} onClick={() => setShowBulk((v) => !v)}>
            <Upload className="mr-1.5 h-4 w-4" />
            Импорт
          </Button>
        </div>

        {showBulk && (
          <div className="mb-4 space-y-2 rounded-lg border bg-muted/20 p-3">
            <p className="text-xs text-muted-foreground">По одному домену на строку (или через запятую).</p>
            <Textarea
              rows={5}
              placeholder={'google.com\nopenai.com'}
              value={bulkText}
              disabled={disabled || adding}
              onChange={(e) => setBulkText(e.target.value)}
            />
            <Button size="sm" disabled={disabled || adding || !bulkText.trim()} onClick={() => void handleBulkAdd()}>
              Импортировать
            </Button>
          </div>
        )}

        <div className="mb-4 flex flex-wrap gap-2">
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-8"
              placeholder="Поиск..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading}>
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Обновить
          </Button>
          <Button size="sm" onClick={() => void handleSync()} disabled={disabled || syncing}>
            Синхронизировать
          </Button>
        </div>

        {filtered.length === 0 ? (
          <EmptyState title="Нет доменов" description="Добавьте домен или импортируйте список." />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th className="px-3 py-2 font-medium">Домен</th>
                  <th className="px-3 py-2 font-medium">Тип</th>
                  <th className="px-3 py-2 font-medium">Статус</th>
                  <th className="w-12 px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const label = domainLabel(item)
                  return (
                    <tr key={label} className="border-t">
                      <td className="px-3 py-2 font-mono">{label}</td>
                      <td className="px-3 py-2 text-muted-foreground">{item.type ?? '—'}</td>
                      <td className="px-3 py-2 text-muted-foreground">
                        {item.enabled === false ? 'выкл.' : item.status ?? (item.enabled ? 'вкл.' : '—')}
                      </td>
                      <td className="px-3 py-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          disabled={disabled || removing}
                          onClick={() => setRemoveTarget(label)}
                          aria-label={`Удалить ${label}`}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </StatusPanel>

      <ConfirmDialog
        open={Boolean(removeTarget)}
        title="Удалить домен?"
        description={removeTarget ? `Домен ${removeTarget} будет удалён из AZ-WARP.` : ''}
        confirmLabel="Удалить"
        destructive
        loading={removing}
        onConfirm={() => void confirmRemove()}
        onOpenChange={(open) => !open && setRemoveTarget(null)}
      />
    </div>
  )
}
