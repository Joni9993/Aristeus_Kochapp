import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'

export default function Register() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    passwordConfirm: '',
    invite_token: params.get('token') ?? '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (form.password !== form.passwordConfirm) {
      setError('Passwörter stimmen nicht überein')
      return
    }
    setLoading(true)
    try {
      await apiFetch('/auth/register', {
        method: 'POST',
        body: {
          username: form.username,
          email: form.email,
          password: form.password,
          invite_token: form.invite_token,
        },
      })
      navigate('/login?registered=1', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Registrierung fehlgeschlagen')
    } finally {
      setLoading(false)
    }
  }

  const field = (
    label: string,
    key: keyof typeof form,
    type = 'text',
    autoComplete?: string,
  ) => (
    <div>
      <label className="mb-1 block text-sm font-medium text-stone-700">{label}</label>
      <input
        type={type}
        className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        autoComplete={autoComplete}
        required
      />
    </div>
  )

  return (
    <main className="flex min-h-screen items-center justify-center bg-stone-50 p-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-2 text-2xl font-semibold tracking-tight">Konto erstellen</h1>
        <p className="mb-6 text-sm text-stone-500">
          Du brauchst einen Einladungs-Token. Wende dich an den Admin.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          {field('Benutzername', 'username', 'text', 'username')}
          {field('E-Mail', 'email', 'email', 'email')}
          {field('Passwort (mind. 8 Zeichen)', 'password', 'password', 'new-password')}
          {field('Passwort wiederholen', 'passwordConfirm', 'password', 'new-password')}
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700">
              Einladungs-Token
            </label>
            <input
              className="w-full rounded-lg border border-stone-300 px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
              value={form.invite_token}
              onChange={(e) => setForm({ ...form, invite_token: e.target.value })}
              required
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? 'Erstelle Konto…' : 'Konto erstellen'}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-stone-500">
          Bereits ein Konto?{' '}
          <Link to="/login" className="underline hover:text-stone-700">
            Anmelden
          </Link>
        </p>
      </div>
    </main>
  )
}
