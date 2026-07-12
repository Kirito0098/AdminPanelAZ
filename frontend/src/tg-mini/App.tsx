import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { TgAuthProvider, useTgAuth } from '@/tg-mini/context/TgAuthContext'
import MiniShell from '@/tg-mini/layout/MiniShell'
import Configs from '@/tg-mini/pages/Configs'
import Cidr from '@/tg-mini/pages/Cidr'
import Dashboard from '@/tg-mini/pages/Dashboard'
import Nodes from '@/tg-mini/pages/Nodes'
import Settings from '@/tg-mini/pages/Settings'
import Warper from '@/tg-mini/pages/Warper'

function HomeRoute() {
  const { isAdmin } = useTgAuth()
  return isAdmin ? <Dashboard /> : <Configs />
}

export default function TgMiniApp() {
  return (
    <TgAuthProvider>
      <HashRouter>
        <Routes>
          <Route element={<MiniShell />}>
            <Route index element={<HomeRoute />} />
            <Route path="configs" element={<Configs />} />
            <Route path="nodes" element={<Nodes />} />
            <Route path="warper" element={<Warper />} />
            <Route path="cidr" element={<Cidr />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </TgAuthProvider>
  )
}
