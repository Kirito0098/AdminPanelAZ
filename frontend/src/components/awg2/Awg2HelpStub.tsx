import { Info } from 'lucide-react'
import type { Awg2HealthResponse } from '@/types'
import { AWG2_INSTALL_CMD } from './utils'

interface Awg2HelpStubProps {
  health: Awg2HealthResponse | null
}

export default function Awg2HelpStub({ health }: Awg2HelpStubProps) {
  const updateCmd = health?.update_command?.trim() || `${AWG2_INSTALL_CMD} --update`

  return (
    <div className="space-y-4 rounded-xl border bg-card/50 p-5">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Info className="h-4 w-4" />
        </div>
        <div className="min-w-0 space-y-2 text-sm">
          <h2 className="text-base font-semibold tracking-tight">Справка</h2>
          <p className="text-muted-foreground">
            AZ-AWG2 — параллельный слой AmneziaWG 2.0 (az-awg2) поверх AntiZapret.
            Штатные WireGuard и стоковый AmneziaWG не затрагиваются.
          </p>
          <div className="space-y-1.5 text-muted-foreground">
            <p>
              <span className="font-medium text-foreground">Vs стоковый AmneziaWG:</span> отдельный
              overlay (`/opt/antizapret-awg`), тип конфига <code className="text-xs">amneziawg2</code>,
              своя вкладка на Dashboard и клиенты через <code className="text-xs">awg-client</code>.
              Вкладка «AmneziaWG» в Конфигурациях остаётся для стока AntiZapret.
            </p>
            <p>
              <span className="font-medium text-foreground">Vs AZ-WARP:</span> WARP точечно гонит
              выбранные домены через Cloudflare. AZ-AWG2 выдаёт полноценные VPN-профили (оба
              туннеля: AntiZapret и полный VPN) для клиентов AmneziaWG 2.0.
            </p>
            <p>
              <span className="font-medium text-foreground">HA:</span> репликация клиентов AWG2 на
              replica поддерживается. Если на replica не установлен слой AZ-AWG2, sync завершится
              ошибкой и вернёт команду установки для этого узла.
            </p>
          </div>
          <p className="text-muted-foreground">
            Во вкладке клиентов доступны список профилей, создание, удаление и скачивание.
            Если слой не установлен на текущем узле или на HA replica, сначала выполните команду
            установки на сервере по SSH. Панель install.sh не запускает.
          </p>
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">Установка:</p>
            <pre className="overflow-x-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs">
              {health?.install_command?.trim() || AWG2_INSTALL_CMD}
            </pre>
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              Обновление слоя (без смены обфускации):
            </p>
            <pre className="overflow-x-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs">{updateCmd}</pre>
          </div>
        </div>
      </div>
    </div>
  )
}
