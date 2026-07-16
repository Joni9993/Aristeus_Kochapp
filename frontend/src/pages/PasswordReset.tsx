import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'

export default function PasswordReset() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [email, setEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleRequest(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await apiFetch('/auth/password-reset/request', { method: 'POST', body: { email } })
      setMessage('Falls die E-Mail bekannt ist, wurde ein Link gesendet.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler')
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await apiFetch('/auth/password-reset/confirm', {
        method: 'POST',
        body: { token, new_password: newPassword },
      })
      setMessage('Passwort geändert. Du kannst dich jetzt anmelden.')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface p-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-6 font-display text-2xl font-semibold tracking-tight text-ink">Passwort zurücksetzen</h1>
        {message ? (
          <div className="space-y-4">
            <p className="text-sm text-olive">{message}</p>
            <Link to="/login" className="text-sm underline text-ink/75 hover:text-ink">
              Zur Anmeldung
            </Link>
          </div>
        ) : token ? (
          <form onSubmit={handleConfirm} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-ink">
                Neues Passwort
              </label>
              <input
                type="password"
                className="w-full rounded-lg border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-olive"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={8}
                required
              />
            </div>
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-olive px-4 py-2 text-sm font-medium text-olive-on hover:bg-olive-hover disabled:opacity-50"
            >
              {loading ? 'Speichern…' : 'Passwort speichern'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleRequest} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-ink">E-Mail</label>
              <input
                type="email"
                className="w-full rounded-lg border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-olive"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-olive px-4 py-2 text-sm font-medium text-olive-on hover:bg-olive-hover disabled:opacity-50"
            >
              {loading ? 'Sende Link…' : 'Reset-Link senden'}
            </button>
          </form>
        )}
      </div>
    </main>
  )
}
