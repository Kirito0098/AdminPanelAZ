import { useEffect, useRef } from 'react'
import { HashRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import FeatureGate from '@/tg-mini/FeatureGate'
import { TgAuthProvider, useTgAuth } from '@/tg-mini/context/TgAuthContext'
import MiniShell from '@/tg-mini/layout/MiniShell'
import { mapTelegramStartParam } from '@/tg-mini/lib/startParam'
import AccessRequests from '@/tg-mini/pages/AccessRequests'
import Clients from '@/tg-mini/pages/Clients'
import Configs from '@/tg-mini/pages/Configs'
import Messages from '@/tg-mini/pages/Messages'
import Settings from '@/tg-mini/pages/Settings'
import UnlockCodes from '@/tg-mini/pages/UnlockCodes'

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
            <Route index element={<Configs />} />
            <Route path="configs" element={<Configs />} />
            <Route path="clients" element={<Clients />} />
            <Route path="requests" element={<AccessRequests />} />
            <Route
              path="messages"
              element={
                <FeatureGate featureKey="user_messaging">
                  <Messages />
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
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </TgAuthProvider>
  )
}
