import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Download, ExternalLink, Shield } from 'lucide-react'
import { fetchPublicPortalMeta, type PortalFileMeta, type PortalMetaResponse } from '@/api/portal'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Spinner from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'

const OS_OPTIONS = [
  { id: 'windows', label: 'Windows' },
  { id: 'android', label: 'Android' },
  { id: 'ios', label: 'iOS' },
  { id: 'mac', label: 'macOS' },
  { id: 'linux', label: 'Linux' },
] as const

function protocolTitle(vpnType: string): string {
  if (vpnType === 'openvpn') return 'OpenVPN'
  if (vpnType === 'wireguard') return 'WireGuard'
  if (vpnType === 'amneziawg2') return 'AmneziaWG 2.0'
  return vpnType
}

function FileActions({ file }: { file: PortalFileMeta }) {
  const isOpenVpn =
    file.vpn_type === 'openvpn' || file.filename.toLowerCase().endsWith('.ovpn')
  return (
    <div className="flex flex-wrap gap-2">
      {isOpenVpn && file.openvpn_import_url && (
        <Button asChild className="gap-1.5">
          <a href={file.openvpn_import_url}>
            <ExternalLink size={16} />
            Добавить в OpenVPN
          </a>
        </Button>
      )}
      <Button asChild variant={isOpenVpn ? 'outline' : 'default'} className="gap-1.5">
        <a href={file.download_url} download={file.filename}>
          <Download size={16} />
          Скачать {isOpenVpn ? '.ovpn' : 'конфиг'}
        </a>
      </Button>
    </div>
  )
}

export default function PortalPage() {
  const { token = '' } = useParams()
  const [data, setData] = useState<PortalMetaResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [os, setOs] = useState<(typeof OS_OPTIONS)[number]['id']>('windows')

  useEffect(() => {
    if (!token) {
      setError('Ссылка недействительна')
      setLoading(false)
      return
    }
    setLoading(true)
    fetchPublicPortalMeta(token)
      .then(setData)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
  }, [token])

  const filesByType = useMemo(() => {
    const map = new Map<string, PortalFileMeta[]>()
    for (const file of data?.files || []) {
      const list = map.get(file.vpn_type) || []
      list.push(file)
      map.set(file.vpn_type, list)
    }
    return map
  }, [data])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Spinner label="Загрузка…" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>Ссылка недоступна</CardTitle>
            <CardDescription>{error || 'Не удалось открыть портал'}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/40">
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
        <header className="space-y-2 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Shield size={24} />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{data.brand_title}</h1>
          <p className="text-sm text-muted-foreground">
            Клиент <span className="font-medium text-foreground">{data.client_name}</span>
            {data.protocols.length > 0 && (
              <> · {data.protocols.map(protocolTitle).join(', ')}</>
            )}
          </p>
        </header>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Установка</CardTitle>
            <CardDescription>Выберите ОС, установите приложение и добавьте профиль</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {OS_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setOs(opt.id)}
                  className={cn(
                    'rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors',
                    os === opt.id
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'hover:bg-muted/60',
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <ol className="list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
              <li>Установите клиент для выбранной платформы ({OS_OPTIONS.find((o) => o.id === os)?.label}).</li>
              <li>
                OpenVPN: нажмите «Добавить в OpenVPN» (нужен OpenVPN Connect 3.3.6+) или скачайте файл.
                WireGuard / AmneziaWG: скачайте конфиг и импортируйте в приложение.
              </li>
              <li>Подключитесь в приложении.</li>
            </ol>
          </CardContent>
        </Card>

        {[...filesByType.entries()].map(([vpnType, files]) => (
          <Card key={vpnType}>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{protocolTitle(vpnType)}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {files.map((file) => (
                <div
                  key={file.path}
                  className="flex flex-col gap-3 rounded-xl border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{file.label}</p>
                    <p className="truncate text-xs text-muted-foreground">{file.filename}</p>
                  </div>
                  <FileActions file={file} />
                </div>
              ))}
            </CardContent>
          </Card>
        ))}

        {data.files.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              Для этого клиента пока нет файлов профиля.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
