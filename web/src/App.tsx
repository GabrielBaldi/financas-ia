import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { useToken } from './api/session'
import { Layout } from './components/Layout'
import { DashboardPage } from './pages/DashboardPage'
import { ImportPage } from './pages/ImportPage'
import { LoginPage } from './pages/LoginPage'
import { ReviewPage } from './pages/ReviewPage'
import { RulesPage } from './pages/RulesPage'

function RequireAuth({ children }: { children: ReactNode }) {
  return useToken() ? children : <Navigate to="/entrar" replace />
}

function GuestOnly({ children }: { children: ReactNode }) {
  return useToken() ? <Navigate to="/revisao" replace /> : children
}

export function App() {
  return (
    <Routes>
      <Route
        path="/entrar"
        element={
          <GuestOnly>
            <LoginPage />
          </GuestOnly>
        }
      />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/revisao" element={<ReviewPage />} />
        <Route path="/painel" element={<DashboardPage />} />
        <Route path="/importar" element={<ImportPage />} />
        <Route path="/regras" element={<RulesPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/revisao" replace />} />
    </Routes>
  )
}
