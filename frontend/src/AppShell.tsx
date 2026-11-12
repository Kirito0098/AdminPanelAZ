import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import ForcePasswordChange from './components/ForcePasswordChange'
import Layout from './components/Layout'
import RouteProgress from './components/RouteProgress'
import FeatureGuardRoute from './components/FeatureGuardRoute'
import RouteRedirect from './components/RouteRedirect'
import LazyPage from './components/LazyPage'
import { useAuth } from './context/AuthContext'
import { FeatureModulesProvider, useFeatureModules } from './context/FeatureModulesContext'
import { NodeProvider } from './context/NodeContext'
import { NotificationCenterProvider } from './context/NotificationCenterContext'
import { ProgressProvider } from './context/ProgressContext'
import { ThemeProvider } from './context/ThemeContext'
import { TimezoneProvider } from './context/TimezoneContext'
import { lazyWithRetry } from './lib/lazyWithRetry'

const DashboardPage = lazyWithRetry(() => import('./pages/DashboardPage'))
const MonitoringPage = lazyWithRetry(() => import('./pages/MonitoringPage'))
const NodesPage = lazyWithRetry(() => import('./pages/NodesPage'))
const RoutingPage = lazyWithRetry(() => import('./pages/RoutingPage'))
const AntizapretConfigPage = lazyWithRetry(() => import('./pages/AntizapretConfigPage'))
const ProxyHubPage = lazyWithRetry(() => import('./pages/ProxyHubPage'))
const WarperPage = lazyWithRetry(() => import('./pages/WarperPage'))
const OpenVpnPanelPage = lazyWithRetry(() => import('./pages/OpenVpnPanelPage'))
const Awg2Page = lazyWithRetry(() => import('./pages/Awg2Page'))
const TelegramPage = lazyWithRetry(() => import('./pages/TelegramPage'))
const SubscriptionPage = lazyWithRetry(() => import('./pages/SubscriptionPage'))
const SettingsPage = lazyWithRetry(() => import('./pages/SettingsPage'))
const EditFilesPage = lazyWithRetry(() => import('./pages/EditFilesPage'))
const UsersPage = lazyWithRetry(() => import('./pages/UsersPage'))
const MessagesPage = lazyWithRetry(() => import('./pages/MessagesPage'))

/** Старый /antizapret разошёлся: setup и панель OpenVPN теперь отдельные страницы. */
/**
 * «Портал и коды» теперь вкладка «Абонентов». Если модуль абонентов выключен,
 * а портал включён, старый /subscription остаётся самостоятельной страницей.
 */
function SubscriptionEntry() {
  const { isEnabled } = useFeatureModules()
  return isEnabled('user_provisioning') ? <Navigate to="/users?tab=portal" replace /> : <SubscriptionPage />
}

function AntizapretRedirect() {
  const { search, hash } = useLocation()
  const params = new URLSearchParams(search)
  const openvpnPanel = params.get('tab') === 'openvpn-panel'
  params.delete('tab')
  const to = openvpnPanel ? '/protocols/openvpn' : '/protocols/antizapret'
  const query = params.toString()
  return <Navigate to={{ pathname: to, search: query, hash }} replace />
}

/** Everything behind login; loaded only once a session exists. */
export default function AppShell() {
  const { user } = useAuth()
  // Until the password is replaced the API answers 403 to everything except /me and change-password.
  if (user?.must_change_password) return <ForcePasswordChange />
  return (
    <FeatureModulesProvider>
      <NotificationCenterProvider>
        <ThemeProvider>
          <TimezoneProvider>
            <ProgressProvider>
              <NodeProvider>
                <RouteProgress />
                <Routes>
                  <Route path="/" element={<Layout />}>
                    <Route index element={<LazyPage><DashboardPage /></LazyPage>} />
                    <Route
                      path="monitoring"
                      element={
                        <LazyPage>
                          <FeatureGuardRoute anyOf={['logs_dashboard', 'traffic_sync', 'server_monitor', 'action_logs']}>
                            <MonitoringPage />
                          </FeatureGuardRoute>
                        </LazyPage>
                      }
                    />
                    <Route path="traffic" element={<RouteRedirect to="/monitoring" tab="traffic" />} />
                    <Route path="routing" element={<LazyPage><FeatureGuardRoute feature="routing"><RoutingPage /></FeatureGuardRoute></LazyPage>} />
                    <Route path="protocols/antizapret" element={<LazyPage><FeatureGuardRoute feature="antizapret_config"><AntizapretConfigPage /></FeatureGuardRoute></LazyPage>} />
                    <Route path="protocols/openvpn" element={<LazyPage><FeatureGuardRoute feature="openvpn"><OpenVpnPanelPage /></FeatureGuardRoute></LazyPage>} />
                    <Route path="protocols/warper" element={<LazyPage><FeatureGuardRoute feature="warper"><WarperPage /></FeatureGuardRoute></LazyPage>} />
                    <Route path="protocols/awg2" element={<LazyPage><FeatureGuardRoute feature="awg2"><Awg2Page /></FeatureGuardRoute></LazyPage>} />
                    <Route path="proxy" element={<LazyPage><FeatureGuardRoute feature="proxy_nodes"><ProxyHubPage /></FeatureGuardRoute></LazyPage>} />
                    <Route path="antizapret" element={<AntizapretRedirect />} />
                    <Route path="warper" element={<RouteRedirect to="/protocols/warper" />} />
                    <Route path="awg2" element={<RouteRedirect to="/protocols/awg2" />} />
                    <Route path="telegram" element={<LazyPage><FeatureGuardRoute feature="telegram"><TelegramPage /></FeatureGuardRoute></LazyPage>} />
                    <Route
                      path="subscription"
                      element={
                        <LazyPage>
                          <FeatureGuardRoute anyOf={['client_portal', 'unlock_codes']}>
                            <SubscriptionEntry />
                          </FeatureGuardRoute>
                        </LazyPage>
                      }
                    />
                    <Route path="edit-files" element={<LazyPage><FeatureGuardRoute feature="edit_files"><EditFilesPage /></FeatureGuardRoute></LazyPage>} />
                    <Route path="logs" element={<RouteRedirect to="/monitoring" tab="logs" paramMap={{ tab: 'log' }} />} />
                    <Route path="server-monitor" element={<RouteRedirect to="/monitoring?scope=host" tab="resources" />} />
                    <Route path="nodes" element={<LazyPage><FeatureGuardRoute feature="nodes"><NodesPage /></FeatureGuardRoute></LazyPage>} />
                    <Route
                      path="users"
                      element={<LazyPage><FeatureGuardRoute feature="user_provisioning"><UsersPage /></FeatureGuardRoute></LazyPage>}
                    />
                    <Route
                      path="users/:userId"
                      element={<LazyPage><FeatureGuardRoute feature="user_provisioning"><UsersPage /></FeatureGuardRoute></LazyPage>}
                    />
                    <Route
                      path="messages"
                      element={<LazyPage><FeatureGuardRoute feature="user_messaging"><MessagesPage /></FeatureGuardRoute></LazyPage>}
                    />
                    <Route path="settings/:section?" element={<LazyPage><SettingsPage /></LazyPage>} />
                  </Route>
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </NodeProvider>
            </ProgressProvider>
          </TimezoneProvider>
        </ThemeProvider>
      </NotificationCenterProvider>
    </FeatureModulesProvider>
  )
}
