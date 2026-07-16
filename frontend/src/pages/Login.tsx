import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
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
    <main className="flex min-h-screen items-center justify-center bg-stone-50 p-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 text-2xl font-semibold tracking-tight">
          Aristeus Kochapp{' '}
          <span className="text-xs font-normal text-stone-400">v{APP_VERSION}</span>
        </h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700">
              Benutzername oder E-Mail
            </label>
            <input
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              value={form.username_or_email}
              onChange={(e) => setForm({ ...form, username_or_email: e.target.value })}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700">Passwort</label>
            <input
              type="password"
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              autoComplete="current-password"
              required
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? 'Anmelden…' : 'Anmelden'}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-stone-500">
          <Link to="/password-reset" className="underline hover:text-stone-700">
            Passwort vergessen?
          </Link>
        </p>
      </div>
    </main>
  )
}
