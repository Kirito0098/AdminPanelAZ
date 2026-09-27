import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { routerBasename } from './lib/panelBase'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import RouteProgress from './components/RouteProgress'
import FeatureGuardRoute from './components/FeatureGuardRoute'
import LazyPage from './components/LazyPage'
import { AuthProvider } from './context/AuthContext'
import { FeatureModulesProvider } from './context/FeatureModulesContext'
import { NodeProvider } from './context/NodeContext'
import { NotificationProvider } from './context/NotificationContext'
import { ProgressProvider } from './context/ProgressContext'
import { ThemeProvider } from './context/ThemeContext'
import { TimezoneProvider } from './context/TimezoneContext'
import { lazyWithRetry } from './lib/lazyWithRetry'
import LoginPage from './pages/LoginPage'

const PortalPage = lazyWithRetry(() => import('./pages/PortalPage'))
const DashboardPage = lazyWithRetry(() => import('./pages/DashboardPage'))
const MonitoringPage = lazyWithRetry(() => import('./pages/MonitoringPage'))
const NodesPage = lazyWithRetry(() => import('./pages/NodesPage'))
const RoutingPage = lazyWithRetry(() => import('./pages/RoutingPage'))
const AntizapretConfigPage = lazyWithRetry(() => import('./pages/AntizapretConfigPage'))
const ProxyHubPage = lazyWithRetry(() => import('./pages/ProxyHubPage'))
const WarperPage = lazyWithRetry(() => import('./pages/WarperPage'))
const Awg2Page = lazyWithRetry(() => import('./pages/Awg2Page'))
const TelegramPage = lazyWithRetry(() => import('./pages/TelegramPage'))
const SubscriptionPage = lazyWithRetry(() => import('./pages/SubscriptionPage'))
const SettingsPage = lazyWithRetry(() => import('./pages/SettingsPage'))
const TrafficPage = lazyWithRetry(() => import('./pages/TrafficPage'))
const EditFilesPage = lazyWithRetry(() => import('./pages/EditFilesPage'))
const LogsPage = lazyWithRetry(() => import('./pages/LogsPage'))
const ServerMonitorPage = lazyWithRetry(() => import('./pages/ServerMonitorPage'))

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
                  path="/p/:token"
                  element={
                    <LazyPage>
                      <PortalPage />
                    </LazyPage>
                  }
                />
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
                  <Route
                    path="subscription"
                    element={
                      <LazyPage>
                        <FeatureGuardRoute anyOf={['client_portal', 'unlock_codes']}>
                          <SubscriptionPage />
                        </FeatureGuardRoute>
                      </LazyPage>
                    }
                  />
                  <Route path="edit-files" element={<LazyPage><FeatureGuardRoute feature="edit_files"><EditFilesPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="logs" element={<LazyPage><FeatureGuardRoute anyOf={['logs_dashboard', 'action_logs']}><LogsPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="server-monitor" element={<LazyPage><FeatureGuardRoute feature="server_monitor"><ServerMonitorPage /></FeatureGuardRoute></LazyPage>} />
                  <Route path="nodes" element={<LazyPage><FeatureGuardRoute feature="nodes"><NodesPage /></FeatureGuardRoute></LazyPage>} />
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
