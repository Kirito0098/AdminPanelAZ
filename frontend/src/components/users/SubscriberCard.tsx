import type { MouseEvent } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  AtSign,
  Ban,
  Calendar,
  CheckCircle2,
  Copy,
  ExternalLink,
  Loader2,
  Network,
  PauseCircle,
  Play,
  Server,
  Shield,
  Trash2,
  UserRound,
} from 'lucide-react'
import type { User } from '@/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { formatDate } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import { DEFAULT_USERS_CARD_VIEW_PREFS, type UsersCardViewPrefs } from '@/lib/usersCardViewPrefs'

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning'
type CardTone = 'active' | 'expiring' | 'expired' | 'suspended' | 'attention' | 'neutral'

type MetaRow = {
  key: string
  icon: LucideIcon
  label: string
  value: string
  tone?: 'default' | 'warning' | 'danger' | 'success'
  wide?: boolean
  mono?: boolean
}

function accessParts(user: User): { text: string; tone: MetaRow['tone']; cardTone: CardTone | null } {
  if (!user.access_until) return { text: 'не задан', tone: 'default', cardTone: null }
  const d = new Date(user.access_until)
  const now = new Date()
  if (d < now) {
    return { text: `истёк ${formatDate(user.access_until)}`, tone: 'danger', cardTone: 'expired' }
  }
  if (d.getTime() <= now.getTime() + 7 * 86400000) {
    return { text: `до ${formatDate(user.access_until)}`, tone: 'warning', cardTone: 'expiring' }
  }
  return { text: formatDate(user.access_until), tone: 'default', cardTone: null }
}

function resolveCardState(user: User): {
  tone: CardTone
  label: string
  variant: BadgeVariant
  icon: LucideIcon
} {
  if (user.suspended_at) {
    return { tone: 'suspended', label: 'Приостановлен', variant: 'destructive', icon: PauseCircle }
  }
  if (user.is_active === false) {
    return { tone: 'neutral', label: 'Отключён', variant: 'outline', icon: Ban }
  }
  const access = accessParts(user)
  if (access.cardTone === 'expired') {
    return { tone: 'expired', label: 'Истёк', variant: 'destructive', icon: AlertTriangle }
  }
  if (access.cardTone === 'expiring') {
    return { tone: 'expiring', label: 'Истекает', variant: 'warning', icon: AlertTriangle }
  }
  const state = user.provision_state ?? 'unmanaged'
  if (state === 'partial') {
    return { tone: 'attention', label: 'Требует внимания', variant: 'warning', icon: AlertTriangle }
  }
  if (state === 'pending') {
    return { tone: 'attention', label: 'Применяется', variant: 'default', icon: Loader2 }
  }
  if (state === 'ok') {
    return { tone: 'active', label: 'Активный', variant: 'success', icon: CheckCircle2 }
  }
  return { tone: 'neutral', label: 'Без набора', variant: 'secondary', icon: Shield }
}

function MetaLine({ row }: { row: MetaRow }) {
  const Icon = row.icon
  return (
    <div
      className={cn(
        'flex min-w-0 items-baseline gap-1.5 text-xs leading-snug',
        row.wide && 'sm:col-span-2',
        row.tone === 'danger' && 'text-destructive',
        row.tone === 'warning' && 'text-amber-700 dark:text-amber-300',
        row.tone === 'success' && 'text-emerald-600 dark:text-emerald-400',
      )}
    >
      <Icon size={12} className="mt-0.5 shrink-0 text-muted-foreground" />
      <span className="shrink-0 text-muted-foreground">{row.label}</span>
      <span
        className={cn(
          'min-w-0 font-medium [overflow-wrap:anywhere]',
          row.mono && 'font-mono text-[11px]',
        )}
      >
        {row.value}
      </span>
    </div>
  )
}

function protocolChipClass(protocol: string): string {
  const p = protocol.toLowerCase()
  if (p.includes('openvpn') || p === 'ovpn') {
    return 'border-sky-500/40 text-sky-600 dark:text-sky-300'
  }
  if (p.includes('wireguard') || p === 'wg' || p.includes('amnezia') || p.includes('awg')) {
    return 'border-orange-500/40 text-orange-600 dark:text-orange-300'
  }
  return 'border-border text-muted-foreground'
}

export interface SubscriberCardProps {
  user: User
  selected?: boolean
  showSelect?: boolean
  onSelectChange?: (checked: boolean) => void
  onOpen: () => void
  viewPrefs?: UsersCardViewPrefs
  actionBusy?: boolean
  onSuspend?: () => void
  onResume?: () => void
  onDelete?: () => void
}

export default function SubscriberCard({
  user,
  selected = false,
  showSelect = false,
  onSelectChange,
  onOpen,
  viewPrefs = DEFAULT_USERS_CARD_VIEW_PREFS,
  actionBusy = false,
  onSuspend,
  onResume,
  onDelete,
}: SubscriberCardProps) {
  const status = resolveCardState(user)
  const StatusIcon = status.icon
  const access = accessParts(user)
  const protocols = user.plan_protocols?.length
    ? user.plan_protocols
    : (user.desired_protocols ?? [])
  const nodeCount = user.plan_node_ids?.length ?? 0
  const nameCount = user.plan_config_count ?? user.plan_config_indexes?.length ?? 0
  const fields = viewPrefs.fields

  const metaRows: MetaRow[] = [
    {
      key: 'access',
      icon: Calendar,
      label: 'Срок',
      value: access.text,
      tone: access.tone,
    },
    {
      key: 'nodes',
      icon: Server,
      label: 'Узлы',
      value: nodeCount > 0 ? String(nodeCount) : '—',
    },
    {
      key: 'base',
      icon: UserRound,
      label: 'База',
      value: user.client_base_name || 'не задана',
      wide: !user.telegram_id,
    },
    ...(user.telegram_id
      ? [
          {
            key: 'tg',
            icon: AtSign,
            label: 'Telegram',
            value: user.telegram_id,
            mono: true,
          } satisfies MetaRow,
        ]
      : []),
    {
      key: 'protocols',
      icon: Shield,
      label: 'Протоколы',
      value: protocols.length ? protocols.join(', ') : '—',
      mono: true,
      wide: true,
    },
    {
      key: 'names',
      icon: Network,
      label: 'Имён',
      value: nameCount > 0 ? String(nameCount) : '—',
    },
    ...(user.active_task_id
      ? [
          {
            key: 'task',
            icon: Loader2,
            label: 'Задача',
            value: 'выполняется…',
            wide: true,
          } satisfies MetaRow,
        ]
      : []),
  ].filter((row) => fields[row.key as keyof typeof fields])

  const copyName = async (e: MouseEvent) => {
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(user.username)
    } catch {
      /* ignore */
    }
  }

  return (
    <Card
      className={cn(
        'relative flex h-full flex-col overflow-hidden rounded-xl border shadow-sm transition-colors hover:border-primary/30 hover:shadow-md',
        selected && showSelect && 'border-primary/40 bg-primary/5',
        status.tone === 'expired' && 'border-destructive/30',
        status.tone === 'expiring' && 'border-amber-500/30',
        status.tone === 'suspended' && 'border-destructive/30',
        status.tone === 'attention' && 'border-amber-500/25',
      )}
    >
      <div
        className={cn(
          'h-0.5 w-full',
          status.tone === 'expired' && 'bg-destructive/70',
          status.tone === 'expiring' && 'bg-amber-500/70',
          status.tone === 'suspended' && 'bg-destructive/70',
          status.tone === 'attention' && 'bg-amber-500/60',
          status.tone === 'active' && 'bg-emerald-500/50',
          status.tone === 'neutral' && 'bg-muted-foreground/25',
        )}
        aria-hidden
      />

      <CardHeader className="space-y-2 p-4 pb-2">
        <div className="flex items-start gap-2">
          {showSelect ? (
            <Checkbox
              checked={selected}
              onCheckedChange={(next) => onSelectChange?.(next === true)}
              aria-label={`Выбрать ${user.username}`}
              className="mt-0.5"
              onClick={(e) => e.stopPropagation()}
            />
          ) : null}
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <CardTitle className="flex min-w-0 items-center gap-1.5 text-sm font-semibold leading-tight">
                <span className="truncate">{user.username}</span>
                <button
                  type="button"
                  title="Копировать логин"
                  onClick={(e) => void copyName(e)}
                  className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-primary"
                >
                  <Copy size={13} />
                </button>
              </CardTitle>
              <Badge variant={status.variant} className="shrink-0 gap-1 px-2 py-0.5 text-[11px]">
                <StatusIcon
                  size={11}
                  className={status.tone === 'attention' && user.provision_state === 'pending' ? 'animate-spin' : undefined}
                />
                {status.label}
              </Badge>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <Badge
            variant={user.role === 'admin' ? 'default' : 'secondary'}
            className="h-5 px-1.5 text-[10px]"
          >
            {user.role === 'admin' ? 'Админ' : 'Абонент'}
          </Badge>
          {protocols.map((protocol) => (
            <span
              key={protocol}
              className={cn(
                'inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium',
                protocolChipClass(protocol),
              )}
            >
              {protocol}
            </span>
          ))}
          {user.traffic_limit_blocked ? (
            <Badge variant="destructive" className="h-5 px-1.5 text-[10px]">
              Лимит трафика
            </Badge>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col space-y-2.5 p-4 pt-0">
        <div className="grid grid-cols-1 gap-x-4 gap-y-1.5 sm:grid-cols-2">
          {metaRows.map((row) => (
            <MetaLine key={row.key} row={row} />
          ))}
        </div>

        <div className="mt-auto flex flex-wrap gap-2 pt-1">
          {user.suspended_at ? (
            onResume ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={onResume}
                disabled={actionBusy}
                aria-label={`Возобновить доступ ${user.username}`}
              >
                <Play size={14} />
                Возобновить
              </Button>
            ) : null
          ) : onSuspend ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={onSuspend}
              disabled={actionBusy}
              aria-label={`Приостановить доступ ${user.username}`}
            >
              <PauseCircle size={14} />
              Приостановить
            </Button>
          ) : null}
          {onDelete ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={onDelete}
              disabled={actionBusy}
              aria-label={`Удалить ${user.username}`}
            >
              <Trash2 size={14} />
              Удалить
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={onOpen}
            aria-label={`Открыть карточку ${user.username}`}
          >
            <ExternalLink size={14} />
            Открыть
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
