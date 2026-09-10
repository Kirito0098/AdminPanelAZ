import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import {
  ArrowLeftRight,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Copy,
  Download,
  ExternalLink,
  Link2,
  Shield,
  UserRound,
} from 'lucide-react'
import { fetchPublicPortalMeta, type PortalFileMeta, type PortalMetaResponse } from '@/api/portal'
import { Button } from '@/components/ui/button'
import Spinner from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'

type OsId = 'windows' | 'android' | 'ios' | 'mac' | 'linux'
type KitStep = 'install' | 'profile' | 'connect'

const OS_OPTIONS: { id: OsId; label: string }[] = [
  { id: 'windows', label: 'Windows' },
  { id: 'android', label: 'Android' },
  { id: 'ios', label: 'iOS' },
  { id: 'mac', label: 'macOS' },
  { id: 'linux', label: 'Linux' },
]

const APP_DOWNLOADS: Record<string, Partial<Record<OsId, { label: string; url: string }>>> = {
  openvpn: {
    windows: { label: 'OpenVPN Connect', url: 'https://openvpn.net/client/' },
    mac: { label: 'OpenVPN Connect', url: 'https://openvpn.net/client/' },
    linux: { label: 'OpenVPN', url: 'https://openvpn.net/community-downloads/' },
    android: {
      label: 'OpenVPN Connect',
      url: 'https://play.google.com/store/apps/details?id=net.openvpn.openvpn',
    },
    ios: { label: 'OpenVPN Connect', url: 'https://apps.apple.com/app/openvpn-connect/id590379981' },
  },
  wireguard: {
    windows: { label: 'WireGuard', url: 'https://www.wireguard.com/install/' },
    mac: { label: 'WireGuard', url: 'https://apps.apple.com/app/wireguard/id1451685025' },
    linux: { label: 'WireGuard', url: 'https://www.wireguard.com/install/' },
    android: {
      label: 'WireGuard',
      url: 'https://play.google.com/store/apps/details?id=com.wireguard.android',
    },
    ios: { label: 'WireGuard', url: 'https://apps.apple.com/app/wireguard/id1441195209' },
  },
  amneziawg: {
    windows: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    mac: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    linux: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    android: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    ios: { label: 'AmneziaWG', url: 'https://apps.apple.com/app/amneziawg/id6478942365' },
  },
  amneziawg2: {
    windows: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    mac: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    linux: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    android: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    ios: { label: 'AmneziaWG', url: 'https://apps.apple.com/app/amneziawg/id6478942365' },
  },
}

function protocolTitle(vpnType: string): string {
  if (vpnType === 'openvpn') return 'OpenVPN'
  if (vpnType === 'wireguard') return 'WireGuard'
  if (vpnType === 'amneziawg') return 'AmneziaWG'
  if (vpnType === 'amneziawg2') return 'AmneziaWG 2.0'
  return vpnType
}

function detectOs(): OsId {
  const ua = navigator.userAgent || ''
  if (/Android/i.test(ua)) return 'android'
  if (/iPhone|iPad|iPod/i.test(ua)) return 'ios'
  if (/Mac OS X|Macintosh/i.test(ua) && !/iPhone|iPad|iPod/i.test(ua)) return 'mac'
  if (/Linux/i.test(ua)) return 'linux'
  return 'windows'
}

function connectHint(protocol: string, os: OsId): string {
  if (protocol === 'openvpn') {
    if (os === 'linux') {
      return 'Подключитесь через NetworkManager или командой sudo openvpn --config <файл>.ovpn.'
    }
    return 'В OpenVPN Connect выберите импортированный профиль и нажмите Connect.'
  }
  if (protocol === 'wireguard') {
    if (os === 'linux') return 'Подключение: sudo wg-quick up <имя>.conf'
    return 'В WireGuard нажмите Activate напротив импортированного туннеля.'
  }
  return 'В AmneziaWG выберите импортированный профиль и подключитесь. Обычный WireGuard не подойдёт.'
}

function profileHint(protocol: string): string {
  if (protocol === 'openvpn') {
    return 'Импортируйте профиль одним нажатием (OpenVPN Connect 3.3.6+) или скачайте .ovpn и откройте в приложении.'
  }
  if (protocol === 'wireguard') {
    return 'Скачайте .conf и импортируйте в WireGuard (Import tunnel from file / из файла).'
  }
  return 'Скачайте конфиг и импортируйте в AmneziaWG (.conf) или AmneziaVPN (.vpn).'
}

/** Prefer OpenVPN → AWG2 → AWG → WG when choosing the initial protocol tab. */
function preferredProtocol(protocols: string[]): string {
  for (const key of ['openvpn', 'amneziawg2', 'amneziawg', 'wireguard']) {
    if (protocols.includes(key)) return key
  }
  return protocols[0] || ''
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value)
    return true
  } catch {
    return false
  }
}

function statusToneClass(status?: string) {
  if (status === 'blocked' || status === 'expired') {
    return 'text-amber-300 bg-amber-500/15 border-amber-500/30'
  }
  return 'text-emerald-300 bg-emerald-500/15 border-emerald-500/30'
}

function StatCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string
  value: string
  icon: ReactNode
  tone?: string
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3.5 backdrop-blur-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-400">{label}</p>
        <span className={cn('inline-flex h-7 w-7 items-center justify-center rounded-lg border', tone)}>
          {icon}
        </span>
      </div>
      <p className="truncate text-base font-semibold text-slate-50 sm:text-lg">{value}</p>
    </div>
  )
}

function KitPanel({
  open,
  onToggle,
  step,
  title,
  children,
}: {
  open: boolean
  onToggle: () => void
  step: number
  title: string
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'overflow-hidden rounded-2xl border transition-colors',
        open ? 'border-cyan-400/40 bg-cyan-400/[0.06]' : 'border-white/10 bg-white/[0.02]',
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3.5 text-left"
      >
        <span
          className={cn(
            'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold',
            open ? 'bg-cyan-400 text-slate-950' : 'bg-white/10 text-slate-200',
          )}
        >
          {step}
        </span>
        <span className="flex-1 text-sm font-semibold text-slate-100">{title}</span>
        <ChevronDown
          size={18}
          className={cn('text-slate-400 transition-transform', open && 'rotate-180')}
        />
      </button>
      {open && <div className="space-y-3 border-t border-white/10 px-4 py-4">{children}</div>}
    </div>
  )
}

function FileActions({
  file,
  onCopied,
}: {
  file: PortalFileMeta
  onCopied: (ok: boolean) => void
}) {
  const isOpenVpn =
    file.vpn_type === 'openvpn' || file.filename.toLowerCase().endsWith('.ovpn')
  return (
    <div className="flex flex-wrap gap-2">
      {isOpenVpn && file.openvpn_import_url && (
        <Button asChild className="gap-1.5 bg-cyan-400 text-slate-950 hover:bg-cyan-300">
          <a href={file.openvpn_import_url}>
            <ExternalLink size={16} />
            Импорт в OpenVPN
          </a>
        </Button>
      )}
      <Button
        asChild
        variant="outline"
        className={cn(
          'gap-1.5 border-white/15 bg-transparent text-slate-100 hover:bg-white/10',
          !isOpenVpn && 'bg-cyan-400 text-slate-950 hover:bg-cyan-300 border-transparent',
        )}
      >
        <a href={file.download_url} download={file.filename}>
          <Download size={16} />
          Скачать
        </a>
      </Button>
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="border-white/15 bg-transparent text-slate-100 hover:bg-white/10"
        title="Скопировать ссылку на файл"
        onClick={async () => onCopied(await copyText(file.download_url))}
      >
        <Copy size={16} />
      </Button>
    </div>
  )
}

export default function PortalPage() {
  const { token = '' } = useParams()
  const [data, setData] = useState<PortalMetaResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [os, setOs] = useState<OsId>(() => detectOs())
  const [protocol, setProtocol] = useState<string>('')
  const [openStep, setOpenStep] = useState<KitStep>('install')
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setError('Ссылка недействительна')
      setLoading(false)
      return
    }
    setLoading(true)
    fetchPublicPortalMeta(token)
      .then((meta) => {
        setData(meta)
        setProtocol(preferredProtocol(meta.protocols.length ? meta.protocols : meta.files.map((f) => f.vpn_type)))
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }, [token])

  useEffect(() => {
    if (!toast) return
    const t = window.setTimeout(() => setToast(null), 2200)
    return () => window.clearTimeout(t)
  }, [toast])

  const filesForProtocol = useMemo(() => {
    if (!data) return []
    return data.files.filter((f) => !protocol || f.vpn_type === protocol)
  }, [data, protocol])

  const appLink = protocol ? APP_DOWNLOADS[protocol]?.[os] : undefined
  const status = data?.status

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#070b14] text-slate-100">
        <Spinner label="Загрузка…" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#070b14] p-6 text-slate-100">
        <div className="max-w-md rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-center">
          <h1 className="text-lg font-semibold">Ссылка недоступна</h1>
          <p className="mt-2 text-sm text-slate-400">{error || 'Не удалось открыть портал'}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#070b14] text-slate-100">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(148,163,184,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.08) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-24 top-10 h-72 w-72 rounded-full bg-cyan-500/20 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-16 bottom-10 h-80 w-80 rounded-full bg-sky-700/20 blur-3xl"
      />

      <div className="relative mx-auto max-w-2xl space-y-5 px-4 py-8 sm:py-12">
        <header className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-cyan-400/30 bg-cyan-400/10 text-cyan-300">
              <Shield size={22} />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold tracking-tight sm:text-2xl">
                {data.brand_title}
              </h1>
              <p className="text-xs text-slate-400">Клиентский портал подключения</p>
            </div>
          </div>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="shrink-0 border-white/15 bg-white/[0.03] text-slate-100 hover:bg-white/10"
            title="Скопировать ссылку портала"
            onClick={async () => {
              const ok = await copyText(window.location.href)
              setToast(ok ? 'Ссылка скопирована' : 'Не удалось скопировать')
            }}
          >
            <Link2 size={16} />
          </Button>
        </header>

        <section className="grid grid-cols-2 gap-3">
          <StatCard
            label="Клиент"
            value={data.client_name}
            icon={<UserRound size={14} />}
            tone="border-sky-400/30 bg-sky-400/10 text-sky-300"
          />
          <StatCard
            label="Статус"
            value={status?.status_label || 'Активна'}
            icon={<CheckCircle2 size={14} />}
            tone={statusToneClass(status?.status)}
          />
          <StatCard
            label="Истекает"
            value={status?.expires_label || 'Бессрочно'}
            icon={<CalendarDays size={14} />}
            tone="border-orange-400/30 bg-orange-400/10 text-orange-300"
          />
          <StatCard
            label="Трафик"
            value={status?.traffic_label || '0 B / ∞'}
            icon={<ArrowLeftRight size={14} />}
            tone="border-teal-400/30 bg-teal-400/10 text-teal-300"
          />
        </section>

        <section className="space-y-4 rounded-3xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-sm sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-base font-semibold">Подключение</h2>
              <p className="text-xs text-slate-400">Три шага: приложение → профиль → соединение</p>
            </div>
            {data.protocols.length > 1 && (
              <div className="flex flex-wrap gap-1.5">
                {(['openvpn', 'amneziawg2', 'amneziawg', 'wireguard'] as const)
                  .filter((p) => data.protocols.includes(p))
                  .concat(data.protocols.filter((p) => !['openvpn', 'amneziawg2', 'amneziawg', 'wireguard'].includes(p)))
                  .map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => {
                      setProtocol(p)
                      setOpenStep('install')
                    }}
                    className={cn(
                      'rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors',
                      protocol === p
                        ? 'border-cyan-400/50 bg-cyan-400/15 text-cyan-200'
                        : 'border-white/10 text-slate-300 hover:bg-white/5',
                    )}
                  >
                    {protocolTitle(p)}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-1.5">
            {OS_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setOs(opt.id)}
                className={cn(
                  'rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors',
                  os === opt.id
                    ? 'border-white/25 bg-white/10 text-white'
                    : 'border-transparent text-slate-400 hover:bg-white/5 hover:text-slate-200',
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className="space-y-2.5">
            <KitPanel
              open={openStep === 'install'}
              onToggle={() => setOpenStep('install')}
              step={1}
              title="Установить приложение"
            >
              <p className="text-sm text-slate-300">
                Установите официальный клиент для {OS_OPTIONS.find((o) => o.id === os)?.label} и{' '}
                {protocolTitle(protocol || 'openvpn')}.
              </p>
              {appLink ? (
                <Button asChild className="gap-1.5 bg-cyan-400 text-slate-950 hover:bg-cyan-300">
                  <a href={appLink.url} target="_blank" rel="noreferrer">
                    <ExternalLink size={16} />
                    Скачать {appLink.label}
                  </a>
                </Button>
              ) : (
                <p className="text-sm text-slate-400">Ссылка на приложение для этой ОС появится после выбора протокола.</p>
              )}
            </KitPanel>

            <KitPanel
              open={openStep === 'profile'}
              onToggle={() => setOpenStep('profile')}
              step={2}
              title="Получить профиль"
            >
              <p className="text-sm text-slate-300">{profileHint(protocol || 'openvpn')}</p>
              {filesForProtocol.length === 0 ? (
                <p className="text-sm text-slate-400">Файлы профиля для этого протокола не найдены.</p>
              ) : (
                filesForProtocol.map((file) => (
                  <div
                    key={file.path}
                    className="space-y-3 rounded-xl border border-white/10 bg-black/20 p-3.5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-100">{file.label}</p>
                      <p className="truncate text-xs text-slate-400">{file.filename}</p>
                    </div>
                    <FileActions
                      file={file}
                      onCopied={(ok) => setToast(ok ? 'Ссылка на файл скопирована' : 'Не удалось скопировать')}
                    />
                  </div>
                ))
              )}
            </KitPanel>

            <KitPanel
              open={openStep === 'connect'}
              onToggle={() => setOpenStep('connect')}
              step={3}
              title="Подключиться"
            >
              <p className="text-sm text-slate-300">{connectHint(protocol || 'openvpn', os)}</p>
              <p className="text-xs text-slate-500">
                Если соединение не поднимается — проверьте, что выбран правильный протокол и приложение
                установлено из официального источника.
              </p>
            </KitPanel>
          </div>
        </section>

        {data.files.length === 0 && (
          <p className="text-center text-sm text-slate-400">Для этого клиента пока нет файлов профиля.</p>
        )}
      </div>

      {toast && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-full border border-white/10 bg-slate-900/95 px-4 py-2 text-xs font-medium text-slate-100 shadow-lg">
          {toast}
        </div>
      )}
    </div>
  )
}
