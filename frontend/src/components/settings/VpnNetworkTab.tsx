import { Globe } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function VpnNetworkTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Globe size={18} />
          Порт, HTTPS и Nginx
        </CardTitle>
        <CardDescription>
          Полная настройка публикации панели из UI запланирована в фазе 17. Сейчас используйте{' '}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">scripts/nginx-setup.sh</code> на сервере.
        </CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Переменные <code className="rounded bg-muted px-1 py-0.5 text-xs">BEHIND_NGINX</code>,{' '}
        <code className="rounded bg-muted px-1 py-0.5 text-xs">DOMAIN</code> и сертификаты задаются при установке
        или через скрипт nginx-setup.
      </CardContent>
    </Card>
  )
}
