import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import RouteProgress from './components/RouteProgress'
import { AuthProvider } from './context/AuthContext'
import { NodeProvider } from './context/NodeContext'
import { NotificationProvider } from './context/NotificationContext'
import { ProgressProvider } from './context/ProgressContext'
import { ThemeProvider } from './context/ThemeContext'
import DashboardPage from './pages/DashboardPage'
import LoginPage from './pages/LoginPage'
import MonitoringPage from './pages/MonitoringPage'
import NodesPage from './pages/NodesPage'
import RoutingPage from './pages/RoutingPage'
import SettingsPage from './pages/SettingsPage'
import TrafficPage from './pages/TrafficPage'
import EditFilesPage from './pages/EditFilesPage'
import LogsPage from './pages/LogsPage'
import ServerMonitorPage from './pages/ServerMonitorPage'

export default function App() {
  return (
    <AuthProvider>
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
                  <Route path="monitoring" element={<MonitoringPage />} />
                  <Route path="traffic" element={<TrafficPage />} />
                  <Route path="routing" element={<RoutingPage />} />
                  <Route path="edit-files" element={<EditFilesPage />} />
                  <Route path="logs" element={<LogsPage />} />
                  <Route path="server-monitor" element={<ServerMonitorPage />} />
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
    </AuthProvider>
  )
}
