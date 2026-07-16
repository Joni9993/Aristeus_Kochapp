import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import { AdminRoute, ProtectedRoute } from './components/ProtectedRoute'
import { AuthProvider } from './hooks/useAuth'
import Admin from './pages/Admin'
import Cookbook from './pages/Cookbook'
import Home from './pages/Home'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'
import PasswordReset from './pages/PasswordReset'
import Plan from './pages/Plan'
import PlanFeedback from './pages/PlanFeedback'
import PlanNew from './pages/PlanNew'
import Profile from './pages/Profile'
import Register from './pages/Register'
import Shopping from './pages/Shopping'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/password-reset" element={<PasswordReset />} />
          <Route path="/onboarding" element={<Onboarding />} />

          {/* Protected — with bottom nav */}
          <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
            <Route path="/" element={<Home />} />
            <Route path="/cookbook" element={<Cookbook />} />
            <Route path="/shopping" element={<Shopping />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/plan/new" element={<PlanNew />} />
            <Route path="/plan/:planId" element={<Plan />} />
            <Route path="/plan/:planId/feedback" element={<PlanFeedback />} />
          </Route>

          {/* Admin — with bottom nav */}
          <Route element={<AdminRoute><AppLayout /></AdminRoute>}>
            <Route path="/admin" element={<Admin />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
