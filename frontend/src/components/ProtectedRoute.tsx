import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { household, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <span className="text-stone-400">Laden…</span>
      </div>
    )
  }

  if (!household) return <Navigate to="/login" replace />

  if (!household.onboarding_complete) return <Navigate to="/onboarding" replace />

  return <>{children}</>
}

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const { household, loading } = useAuth()

  if (loading) return null
  if (!household) return <Navigate to="/login" replace />
  if (!household.is_admin) return <Navigate to="/" replace />

  return <>{children}</>
}
