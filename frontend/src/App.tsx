import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { routerBasename } from './lib/panelBase'
import LazyPage from './components/LazyPage'
import ProtectedRoute from './components/ProtectedRoute'
import { AuthProvider } from './context/AuthContext'
import { NotificationProvider } from './context/NotificationContext'
import { lazyWithRetry } from './lib/lazyWithRetry'
import LoginPage from './pages/LoginPage'

// The entry bundle must stay neutral for anonymous visitors (see scripts/check-entry-chunks.mjs):
// panel pages, layout and their providers live in AppShell, loaded only after login.
const AppShell = lazyWithRetry(() => import('./AppShell'))
const PortalPage = lazyWithRetry(() => import('./pages/PortalPage'))

export default function App() {
  return (
    <AuthProvider>
      <NotificationProvider>
        <BrowserRouter basename={routerBasename}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/p/:token"
              element={
                <LazyPage>
                  <PortalPage />
                </LazyPage>
              }
            />
            <Route
              path="*"
              element={
                <ProtectedRoute>
                  <LazyPage>
                    <AppShell />
                  </LazyPage>
                </ProtectedRoute>
              }
            />
          </Routes>
        </BrowserRouter>
      </NotificationProvider>
    </AuthProvider>
  )
}
