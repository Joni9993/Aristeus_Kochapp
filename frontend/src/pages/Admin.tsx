import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

type HouseholdRow = {
  id: number; username: string; email: string; is_admin: boolean
  created_at: string; last_login_at: string | null; has_profile: boolean; onboarding_complete: boolean
  api_calls_count: number; total_tokens: number
}

type ProfileData = {
  postal_code: string; adults: number; kids: number; diet: string
  allergies: string[]; no_gos: string[]; preferred_cuisines: string[]
  allowed_meats: string[]; max_cook_time_min: number; selected_stores: string[]
  budget_sensitivity: number
}

type PrefsData = {
  loved_dishes: string[]; disliked_dishes: string[]
  portion_adjustments: Record<string, string>; recurring_notes: string | null
}

type HouseholdDetails = { profile: ProfileData | null; learned_preferences: PrefsData | null }

type TokenRow = { token: string; created_at: string; used_by: number | null; used_at: string | null }

export default function Admin() {
  const { household } = useAuth()
  const [households, setHouseholds] = useState<HouseholdRow[]>([])
  const [tokens, setTokens] = useState<TokenRow[]>([])
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [details, setDetails] = useState<Record<number, HouseholdDetails>>({})
  const frontendUrl = window.location.origin

  useEffect(() => {
    Promise.all([
      apiFetch<HouseholdRow[]>('/admin/households'),
      apiFetch<TokenRow[]>('/admin/invite-tokens'),
    ]).then(([h, t]) => { setHouseholds(h); setTokens(t) }).catch(() => {})
  }, [])

  async function toggleRow(id: number) {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id)
    if (!details[id]) {
      const d = await apiFetch<HouseholdDetails>(`/admin/households/${id}/details`).catch(() => null)
      if (d) setDetails(prev => ({ ...prev, [id]: d }))
    }
  }

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
    <main className="mx-auto max-w-3xl p-6">
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
        <p className="mb-2 text-xs text-stone-400">Zeile anklicken für Profil & Präferenzen</p>
        <div className="overflow-hidden rounded-xl border border-stone-200">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 text-xs uppercase text-stone-500">
              <tr>
                <th className="px-3 py-2 text-left">Nutzer</th>
                <th className="px-3 py-2 text-left">E-Mail</th>
                <th className="px-3 py-2 text-left">Onboarding</th>
                <th className="px-3 py-2 text-left">Erstellt</th>
                <th className="px-3 py-2 text-right">API-Calls</th>
                <th className="px-3 py-2 text-right">Tokens</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {households.map(h => (
                <>
                  <tr
                    key={h.id}
                    onClick={() => toggleRow(h.id)}
                    className="cursor-pointer hover:bg-stone-50"
                  >
                    <td className="px-3 py-2">
                      <span className="mr-1 text-stone-400">{expanded === h.id ? '▼' : '▶'}</span>
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
                    <td className="px-3 py-2 text-right text-stone-500">{h.api_calls_count}</td>
                    <td className="px-3 py-2 text-right text-stone-500">
                      {h.total_tokens > 0 ? h.total_tokens.toLocaleString('de-DE') : '–'}
                    </td>
                  </tr>
                  {expanded === h.id && (
                    <tr key={`${h.id}-detail`}>
                      <td colSpan={6} className="bg-stone-50 px-4 py-3">
                        <HouseholdDetailPanel detail={details[h.id] ?? null} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  )
}

function HouseholdDetailPanel({ detail }: { detail: HouseholdDetails | null }) {
  if (!detail) return <p className="text-xs text-stone-400">Lädt…</p>

  const { profile: p, learned_preferences: lp } = detail

  return (
    <div className="grid grid-cols-2 gap-6 text-xs">
      <div>
        <p className="mb-1 font-semibold text-stone-600">Profil</p>
        {!p ? (
          <p className="text-stone-400">Kein Profil</p>
        ) : (
          <dl className="space-y-0.5 text-stone-600">
            <Row label="PLZ" value={p.postal_code || '–'} />
            <Row label="Haushalt" value={`${p.adults} Erw. / ${p.kids} Kinder`} />
            <Row label="Ernährung" value={p.diet} />
            <Row label="Max. Kochzeit" value={`${p.max_cook_time_min} Min`} />
            <Row label="Angebots-Prio" value={String(p.budget_sensitivity) + '/5'} />
            <Row label="Läden" value={p.selected_stores.join(', ') || '–'} />
            {p.allergies.length > 0 && <Row label="Allergien" value={p.allergies.join(', ')} />}
            {p.no_gos.length > 0 && <Row label="No-Gos" value={p.no_gos.join(', ')} />}
            {p.preferred_cuisines.length > 0 && <Row label="Küchen" value={p.preferred_cuisines.join(', ')} />}
          </dl>
        )}
      </div>

      <div>
        <p className="mb-1 font-semibold text-stone-600">Gelernte Präferenzen</p>
        {!lp ? (
          <p className="text-stone-400">Noch keine Präferenzen</p>
        ) : (
          <dl className="space-y-0.5 text-stone-600">
            <Row label="Beliebt" value={lp.loved_dishes.join(', ') || '–'} />
            <Row label="Nicht gemocht" value={lp.disliked_dishes.join(', ') || '–'} />
            {Object.keys(lp.portion_adjustments).length > 0 && (
              <Row label="Portionen" value={Object.entries(lp.portion_adjustments).map(([k, v]) => `${k}: ${v}`).join(', ')} />
            )}
            {lp.recurring_notes && <Row label="Notizen" value={lp.recurring_notes} />}
          </dl>
        )}
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-28 shrink-0 text-stone-400">{label}</dt>
      <dd className="break-words">{value}</dd>
    </div>
  )
}
