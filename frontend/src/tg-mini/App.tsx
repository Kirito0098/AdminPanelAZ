import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { TgAuthProvider } from '@/tg-mini/context/TgAuthContext'
import MiniShell from '@/tg-mini/layout/MiniShell'
import Configs from '@/tg-mini/pages/Configs'
import Dashboard from '@/tg-mini/pages/Dashboard'
import Nodes from '@/tg-mini/pages/Nodes'
import Settings from '@/tg-mini/pages/Settings'

export default function TgMiniApp() {
  return (
    <TgAuthProvider>
      <HashRouter>
        <Routes>
          <Route element={<MiniShell />}>
            <Route index element={<Dashboard />} />
            <Route path="configs" element={<Configs />} />
            <Route path="nodes" element={<Nodes />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </TgAuthProvider>
  )
}
