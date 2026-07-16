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
  const [privacyAccepted, setPrivacyAccepted] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (form.password !== form.passwordConfirm) {
      setError('Passwörter stimmen nicht überein')
      return
    }
    if (!privacyAccepted) {
      setError('Bitte stimme der Datenschutzerklärung zu.')
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
      <label className="mb-1 block text-sm font-medium text-ink">{label}</label>
      <input
        type={type}
        className="w-full rounded-lg border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-olive"
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        autoComplete={autoComplete}
        required
      />
    </div>
  )

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface p-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-2 font-display text-2xl font-semibold tracking-tight text-ink">Konto erstellen</h1>
        <p className="mb-6 text-sm text-muted">
          Du brauchst einen Einladungs-Token. Wende dich an den Admin.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          {field('Benutzername', 'username', 'text', 'username')}
          {field('E-Mail', 'email', 'email', 'email')}
          {field('Passwort (mind. 8 Zeichen)', 'password', 'password', 'new-password')}
          {field('Passwort wiederholen', 'passwordConfirm', 'password', 'new-password')}
          <div>
            <label className="mb-1 block text-sm font-medium text-ink">
              Einladungs-Token
            </label>
            <input
              className="w-full rounded-lg border border-line px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-olive"
              value={form.invite_token}
              onChange={(e) => setForm({ ...form, invite_token: e.target.value })}
              required
            />
          </div>
          <label className="flex items-start gap-2 text-sm text-ink/75">
            <input
              type="checkbox"
              checked={privacyAccepted}
              onChange={e => setPrivacyAccepted(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-olive"
            />
            <span>
              Ich habe die{' '}
              <a href="/privacy" target="_blank" className="underline hover:text-ink">
                Datenschutzerklärung
              </a>{' '}
              gelesen und stimme der Verarbeitung meiner Daten zu.
            </span>
          </label>
          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={loading || !privacyAccepted}
            className="w-full rounded-lg bg-olive px-4 py-2 text-sm font-medium text-olive-on hover:bg-olive-hover disabled:opacity-50"
          >
            {loading ? 'Erstelle Konto…' : 'Konto erstellen'}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-muted">
          Bereits ein Konto?{' '}
          <Link to="/login" className="underline hover:text-ink">
            Anmelden
          </Link>
        </p>
      </div>
    </main>
  )
}
