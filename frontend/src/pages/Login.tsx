import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import Laurel from '../components/Laurel'
import { useAuth } from '../hooks/useAuth'
import { APP_VERSION } from '../version'

export default function Login() {
  const navigate = useNavigate()
  const { refresh } = useAuth()
  const [form, setForm] = useState({ username_or_email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await apiFetch<{ ok: boolean; onboarding_complete: boolean }>('/auth/login', {
        method: 'POST',
        body: form,
      })
      await refresh()
      navigate(res.onboarding_complete ? '/' : '/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Anmeldung fehlgeschlagen')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface p-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 flex items-baseline gap-2 font-display text-2xl font-semibold tracking-tight text-ink">
          <Laurel className="h-5 w-5 shrink-0 -scale-x-100 text-olive" />
          Aristeus Kochapp{' '}
          <span className="text-xs font-sans font-normal text-muted">v{APP_VERSION}</span>
        </h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              Benutzername oder E-Mail
            </label>
            <input
              className="w-full rounded-lg border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-olive"
              value={form.username_or_email}
              onChange={(e) => setForm({ ...form, username_or_email: e.target.value })}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">Passwort</label>
            <input
              type="password"
              className="w-full rounded-lg border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-olive"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              autoComplete="current-password"
              required
            />
          </div>
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-olive px-4 py-2 text-sm font-medium text-olive-on hover:bg-olive-hover disabled:opacity-50"
          >
            {loading ? 'Anmelden…' : 'Anmelden'}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-muted">
          <Link to="/password-reset" className="underline hover:text-ink">
            Passwort vergessen?
          </Link>
        </p>
      </div>
    </main>
  )
}
