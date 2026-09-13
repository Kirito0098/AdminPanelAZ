import { useEffect, useRef } from 'react'
import { HashRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import FeatureGate from '@/tg-mini/FeatureGate'
import { TgAuthProvider, useTgAuth } from '@/tg-mini/context/TgAuthContext'
import MiniShell from '@/tg-mini/layout/MiniShell'
import { mapTelegramStartParam } from '@/tg-mini/lib/startParam'
import Awg2 from '@/tg-mini/pages/Awg2'
import Configs from '@/tg-mini/pages/Configs'
import Cidr from '@/tg-mini/pages/Cidr'
import Dashboard from '@/tg-mini/pages/Dashboard'
import Nodes from '@/tg-mini/pages/Nodes'
import UnlockCodes from '@/tg-mini/pages/UnlockCodes'
import Settings from '@/tg-mini/pages/Settings'
import Warper from '@/tg-mini/pages/Warper'

function HomeRoute() {
  const { isAdmin } = useTgAuth()
  return isAdmin ? <Dashboard /> : <Configs />
}

function StartParamRedirect() {
  const { status } = useTgAuth()
  const navigate = useNavigate()
  const handledRef = useRef(false)

  useEffect(() => {
    if (status !== 'authenticated' || handledRef.current) return

    handledRef.current = true
    const startParam = window.Telegram?.WebApp?.initDataUnsafe?.start_param
    const target = mapTelegramStartParam(typeof startParam === 'string' ? startParam : null)
    if (target) {
      navigate(target, { replace: true })
    }
  }, [navigate, status])

  return null
}

export default function TgMiniApp() {
  return (
    <TgAuthProvider>
      <HashRouter>
        <StartParamRedirect />
        <Routes>
          <Route element={<MiniShell />}>
            <Route index element={<HomeRoute />} />
            <Route path="configs" element={<Configs />} />
            <Route path="nodes" element={<Nodes />} />
            <Route
              path="warper"
              element={
                <FeatureGate featureKey="warper">
                  <Warper />
                </FeatureGate>
              }
            />
            <Route
              path="awg2"
              element={
                <FeatureGate featureKey="awg2">
                  <Awg2 />
                </FeatureGate>
              }
            />
            <Route
              path="unlock-codes"
              element={
                <FeatureGate featureKey="unlock_codes">
                  <UnlockCodes />
                </FeatureGate>
              }
            />
            <Route path="cidr" element={<Cidr />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </TgAuthProvider>
  )
}
