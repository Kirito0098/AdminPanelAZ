import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import RouteProgress from './components/RouteProgress'
import FeatureGuardRoute from './components/FeatureGuardRoute'
import { AuthProvider } from './context/AuthContext'
import { FeatureModulesProvider } from './context/FeatureModulesContext'
import { NodeProvider } from './context/NodeContext'
import { NotificationProvider } from './context/NotificationContext'
import { ProgressProvider } from './context/ProgressContext'
import { ThemeProvider } from './context/ThemeContext'
import DashboardPage from './pages/DashboardPage'
import LoginPage from './pages/LoginPage'
import MonitoringPage from './pages/MonitoringPage'
import NodesPage from './pages/NodesPage'
import RoutingPage from './pages/RoutingPage'
import WarperPage from './pages/WarperPage'
import SettingsPage from './pages/SettingsPage'
import TrafficPage from './pages/TrafficPage'
import EditFilesPage from './pages/EditFilesPage'
import LogsPage from './pages/LogsPage'
import ServerMonitorPage from './pages/ServerMonitorPage'

export default function App() {
  return (
    <AuthProvider>
      <FeatureModulesProvider>
      <ThemeProvider>
        <NotificationProvider>
          <ProgressProvider>
            <NodeProvider>
            <BrowserRouter>
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
                  <Route index element={<DashboardPage />} />
                  <Route path="monitoring" element={<FeatureGuardRoute feature="logs_dashboard"><MonitoringPage /></FeatureGuardRoute>} />
                  <Route path="traffic" element={<FeatureGuardRoute feature="traffic_sync"><TrafficPage /></FeatureGuardRoute>} />
                  <Route path="routing" element={<FeatureGuardRoute feature="routing"><RoutingPage /></FeatureGuardRoute>} />
                  <Route path="warper" element={<FeatureGuardRoute feature="warper"><WarperPage /></FeatureGuardRoute>} />
                  <Route path="edit-files" element={<FeatureGuardRoute feature="edit_files"><EditFilesPage /></FeatureGuardRoute>} />
                  <Route path="logs" element={<FeatureGuardRoute anyOf={['logs_dashboard', 'action_logs']}><LogsPage /></FeatureGuardRoute>} />
                  <Route path="server-monitor" element={<FeatureGuardRoute feature="server_monitor"><ServerMonitorPage /></FeatureGuardRoute>} />
                  <Route path="nodes" element={<NodesPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </BrowserRouter>
            </NodeProvider>
          </ProgressProvider>
        </NotificationProvider>
      </ThemeProvider>
      </FeatureModulesProvider>
    </AuthProvider>
  )
}
