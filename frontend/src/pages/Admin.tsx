import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

type HouseholdRow = {
  id: number; username: string; email: string; is_admin: boolean
  created_at: string; last_login_at: string | null; has_profile: boolean; onboarding_complete: boolean
}
type TokenRow = { token: string; created_at: string; used_by: number | null; used_at: string | null }

export default function Admin() {
  const { household } = useAuth()
  const [households, setHouseholds] = useState<HouseholdRow[]>([])
  const [tokens, setTokens] = useState<TokenRow[]>([])
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')
  const frontendUrl = window.location.origin

  useEffect(() => {
    Promise.all([
      apiFetch<HouseholdRow[]>('/admin/households'),
      apiFetch<TokenRow[]>('/admin/invite-tokens'),
    ]).then(([h, t]) => { setHouseholds(h); setTokens(t) }).catch(() => {})
  }, [])

  async function createToken() {
    setCreating(true); setError('')
    try {
      const t = await apiFetch<TokenRow>('/admin/invite-tokens', { method: 'POST' })
      setTokens([t, ...tokens])
    } catch (err) { setError(err instanceof ApiError ? err.message : 'Fehler') }
    finally { setCreating(false) }
  }

  async function revokeToken(token: string) {
    await apiFetch(`/admin/invite-tokens/${token}`, { method: 'DELETE' }).catch(() => {})
    setTokens(tokens.filter(t => t.token !== token))
  }

  function copyLink(token: string) {
    navigator.clipboard.writeText(`${frontendUrl}/register?token=${token}`)
    setCopied(token)
    setTimeout(() => setCopied(''), 2000)
  }

  return (
    <main className="mx-auto max-w-2xl p-6">
      <div className="mb-6 flex items-center gap-4">
        <Link to="/" className="text-sm text-stone-500 underline hover:text-stone-700">← Zurück</Link>
        <h1 className="text-xl font-semibold">Admin-Übersicht</h1>
        <span className="ml-auto text-sm text-stone-500">{household?.username}</span>
      </div>

      <section className="mb-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Einladungs-Tokens</h2>
          <button onClick={createToken} disabled={creating}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
            {creating ? '…' : '+ Neuer Token'}
          </button>
        </div>
        {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
        {tokens.length === 0 ? (
          <p className="text-sm text-stone-400">Noch keine Tokens erstellt.</p>
        ) : (
          <div className="space-y-2">
            {tokens.map(t => (
              <div key={t.token} className={`flex items-center justify-between rounded-lg border px-3 py-2 text-sm ${t.used_by ? 'border-stone-200 bg-stone-50 opacity-60' : 'border-emerald-200 bg-emerald-50'}`}>
                <code className="font-mono text-xs">{t.token}</code>
                <div className="flex items-center gap-2">
                  {t.used_by ? (
                    <span className="text-xs text-stone-400">Verwendet</span>
                  ) : (
                    <>
                      <button onClick={() => copyLink(t.token)} className="text-xs text-emerald-700 underline hover:text-emerald-900">
                        {copied === t.token ? 'Kopiert!' : 'Link kopieren'}
                      </button>
                      <button onClick={() => revokeToken(t.token)} className="text-xs text-red-500 underline hover:text-red-700">Widerrufen</button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 font-semibold">Haushalte ({households.length})</h2>
        <div className="overflow-hidden rounded-xl border border-stone-200">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-xs uppercase text-stone-500">
              <tr>
                <th className="px-3 py-2 text-left">Nutzer</th>
                <th className="px-3 py-2 text-left">E-Mail</th>
                <th className="px-3 py-2 text-left">Onboarding</th>
                <th className="px-3 py-2 text-left">Erstellt</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {households.map(h => (
                <tr key={h.id} className="hover:bg-stone-50">
                  <td className="px-3 py-2">
                    {h.username}
                    {h.is_admin && <span className="ml-1 text-xs text-amber-600">(Admin)</span>}
                  </td>
                  <td className="px-3 py-2 text-stone-600">{h.email}</td>
                  <td className="px-3 py-2">
                    {h.onboarding_complete
                      ? <span className="text-emerald-600">✓ Fertig</span>
                      : <span className="text-stone-400">Ausstehend</span>}
                  </td>
                  <td className="px-3 py-2 text-stone-500">
                    {new Date(h.created_at).toLocaleDateString('de-DE')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}
