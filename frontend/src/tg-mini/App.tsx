import { useEffect, useRef } from 'react'
import { HashRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import LazyPage from '@/components/LazyPage'
import { lazyWithRetry } from '@/lib/lazyWithRetry'
import AdminGate from '@/tg-mini/AdminGate'
import FeatureGate from '@/tg-mini/FeatureGate'
import { TgAuthProvider, useTgAuth } from '@/tg-mini/context/TgAuthContext'
import MiniShell from '@/tg-mini/layout/MiniShell'
import { mapTelegramStartParam } from '@/tg-mini/lib/startParam'
import Configs from '@/tg-mini/pages/Configs'

// Only the shell, navigation and the configs screen belong to the entry bundle.
// The backend serves these chunks only to a Mini App that already signed in
// (backend/app/routers/tg_mini/static.py), so every admin/extra screen is lazy.
const AccessRequests = lazyWithRetry(() => import('@/tg-mini/pages/AccessRequests'))
const Clients = lazyWithRetry(() => import('@/tg-mini/pages/Clients'))
const Messages = lazyWithRetry(() => import('@/tg-mini/pages/Messages'))
const Settings = lazyWithRetry(() => import('@/tg-mini/pages/Settings'))
const UnlockCodes = lazyWithRetry(() => import('@/tg-mini/pages/UnlockCodes'))

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
            <Route
              path="clients"
              element={
                <AdminGate>
                  <LazyPage>
                    <Clients />
                  </LazyPage>
                </AdminGate>
              }
            />
            <Route
              path="requests"
              element={
                <AdminGate>
                  <LazyPage>
                    <AccessRequests />
                  </LazyPage>
                </AdminGate>
              }
            />
            <Route
              path="messages"
              element={
                <FeatureGate featureKey="user_messaging">
                  <LazyPage>
                    <Messages />
                  </LazyPage>
                </FeatureGate>
              }
            />
            <Route
              path="unlock-codes"
              element={
                <FeatureGate featureKey="unlock_codes">
                  <AdminGate>
                    <LazyPage>
                      <UnlockCodes />
                    </LazyPage>
                  </AdminGate>
                </FeatureGate>
              }
            />
            <Route
              path="settings"
              element={
                <LazyPage>
                  <Settings />
                </LazyPage>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </TgAuthProvider>
  )
}
