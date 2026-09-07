import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { routerBasename } from './lib/panelBase'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import RouteProgress from './components/RouteProgress'
import FeatureGuardRoute from './components/FeatureGuardRoute'
import ErrorBoundary from './components/ErrorBoundary'
import Spinner from './components/ui/Spinner'
import { AuthProvider } from './context/AuthContext'
import { FeatureModulesProvider } from './context/FeatureModulesContext'
import { NodeProvider } from './context/NodeContext'
import { NotificationProvider } from './context/NotificationContext'
import { ProgressProvider } from './context/ProgressContext'
import { ThemeProvider } from './context/ThemeContext'
import { TimezoneProvider } from './context/TimezoneContext'
import LoginPage from './pages/LoginPage'

const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const MonitoringPage = lazy(() => import('./pages/MonitoringPage'))
const NodesPage = lazy(() => import('./pages/NodesPage'))
const RoutingPage = lazy(() => import('./pages/RoutingPage'))
const AntizapretConfigPage = lazy(() => import('./pages/AntizapretConfigPage'))
const ProxyHubPage = lazy(() => import('./pages/ProxyHubPage'))
const WarperPage = lazy(() => import('./pages/WarperPage'))
const Awg2Page = lazy(() => import('./pages/Awg2Page'))
const TelegramPage = lazy(() => import('./pages/TelegramPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const TrafficPage = lazy(() => import('./pages/TrafficPage'))
const EditFilesPage = lazy(() => import('./pages/EditFilesPage'))
const LogsPage = lazy(() => import('./pages/LogsPage'))
const ServerMonitorPage = lazy(() => import('./pages/ServerMonitorPage'))

function PageFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <Spinner label="Загрузка…" />
    </div>
  )
}

function LazyPage({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<PageFallback />}>{children}</Suspense>
    </ErrorBoundary>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <FeatureModulesProvider>
      <ThemeProvider>
      <TimezoneProvider>
        <NotificationProvider>
          <ProgressProvider>
            <NodeProvider>
            <BrowserRouter basename={routerBasename}>
              <RouteProgress />
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route
                  path="/"
                  element={
                    <ProtectedRoute>
                      <Layout />
                    </ProtectedRoute>
                  }
                >
                  <Route index element={<LazyPage><DashboardPage /></LazyPage>} />
                  <Route path="monitoring" element={<LazyPage><FeatureGuardRoute feature="logs_dashboard"><MonitoringPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="traffic" element={<LazyPage><FeatureGuardRoute feature="traffic_sync"><TrafficPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="routing" element={<LazyPage><FeatureGuardRoute feature="routing"><RoutingPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="antizapret" element={<LazyPage><FeatureGuardRoute feature="antizapret_config"><AntizapretConfigPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="proxy" element={<LazyPage><FeatureGuardRoute feature="proxy_nodes"><ProxyHubPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="warper" element={<LazyPage><FeatureGuardRoute feature="warper"><WarperPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="awg2" element={<LazyPage><FeatureGuardRoute feature="awg2"><Awg2Page /></FeatureGuardRoute></LazyPage>} />
                  <Route path="telegram" element={<LazyPage><FeatureGuardRoute feature="telegram"><TelegramPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="edit-files" element={<LazyPage><FeatureGuardRoute feature="edit_files"><EditFilesPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="logs" element={<LazyPage><FeatureGuardRoute anyOf={['logs_dashboard', 'action_logs']}><LogsPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="server-monitor" element={<LazyPage><FeatureGuardRoute feature="server_monitor"><ServerMonitorPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="nodes" element={<LazyPage><NodesPage /></LazyPage>} />
                  <Route path="settings/:section?" element={<LazyPage><SettingsPage /></LazyPage>} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
            </NodeProvider>
          </ProgressProvider>
        </NotificationProvider>
      </TimezoneProvider>
      </ThemeProvider>
      </FeatureModulesProvider>
    </AuthProvider>
  )
}
