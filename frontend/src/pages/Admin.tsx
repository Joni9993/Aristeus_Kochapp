import { useEffect, useState } from 'react'
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
    <main className="mx-auto max-w-xl p-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Admin</h1>
        <p className="text-sm text-stone-500">{household?.username}</p>
      </div>

      {/* Einladungs-Tokens */}
      <section className="mb-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">Einladungs-Tokens</h2>
          <button
            onClick={createToken}
            disabled={creating}
            className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {creating ? '…' : '+ Token'}
          </button>
        </div>
        {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
        {tokens.length === 0 ? (
          <p className="text-sm text-stone-400">Noch keine Tokens erstellt.</p>
        ) : (
          <div className="space-y-2">
            {tokens.map(t => (
              <div
                key={t.token}
                className={`rounded-xl border p-3 ${t.used_by ? 'border-stone-200 bg-stone-50 opacity-60' : 'border-emerald-200 bg-emerald-50'}`}
              >
                <code className="block font-mono text-xs break-all text-stone-700">{t.token}</code>
                <div className="mt-2 flex items-center gap-3">
                  {t.used_by ? (
                    <span className="text-xs text-stone-400">Verwendet</span>
                  ) : (
                    <>
                      <button
                        onClick={() => copyLink(t.token)}
                        className="text-sm font-medium text-emerald-700 active:text-emerald-900"
                      >
                        {copied === t.token ? '✓ Kopiert' : 'Link kopieren'}
                      </button>
                      <button
                        onClick={() => revokeToken(t.token)}
                        className="text-sm text-red-500 active:text-red-700"
                      >
                        Widerrufen
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Haushalte */}
      <section>
        <h2 className="mb-3 font-semibold">Haushalte ({households.length})</h2>
        <div className="space-y-2">
          {households.map(h => (
            <div key={h.id}>
              <button
                onClick={() => toggleRow(h.id)}
                className="w-full rounded-xl border border-stone-200 bg-white px-4 py-3 text-left active:bg-stone-50"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-stone-800">{h.username}</span>
                      {h.is_admin && (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">Admin</span>
                      )}
                      <span className={`rounded-full px-2 py-0.5 text-xs ${h.onboarding_complete ? 'bg-emerald-100 text-emerald-700' : 'bg-stone-100 text-stone-500'}`}>
                        {h.onboarding_complete ? '✓ Fertig' : 'Ausstehend'}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-stone-500 truncate">{h.email}</p>
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-stone-400">
                      <span>{h.api_calls_count} API-Calls</span>
                      {h.total_tokens > 0 && (
                        <span>{h.total_tokens.toLocaleString('de-DE')} Tokens</span>
                      )}
                      <span>seit {new Date(h.created_at).toLocaleDateString('de-DE')}</span>
                    </div>
                  </div>
                  <span className="mt-1 shrink-0 text-stone-400 text-sm">
                    {expanded === h.id ? '▼' : '▶'}
                  </span>
                </div>
              </button>

              {expanded === h.id && (
                <div className="rounded-b-xl border-x border-b border-stone-200 bg-stone-50 px-4 py-3 -mt-1">
                  <HouseholdDetailPanel detail={details[h.id] ?? null} />
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}

function HouseholdDetailPanel({ detail }: { detail: HouseholdDetails | null }) {
  if (!detail) return <p className="text-xs text-stone-400">Lädt…</p>

  const { profile: p, learned_preferences: lp } = detail

  return (
    <div className="space-y-4 text-xs">
      <div>
        <p className="mb-1.5 font-semibold text-stone-600">Profil</p>
        {!p ? (
          <p className="text-stone-400">Kein Profil</p>
        ) : (
          <dl className="space-y-1 text-stone-600">
            <Row label="PLZ" value={p.postal_code || '–'} />
            <Row label="Haushalt" value={`${p.adults} Erw. / ${p.kids} Kinder`} />
            <Row label="Ernährung" value={p.diet} />
            <Row label="Max. Kochzeit" value={`${p.max_cook_time_min} Min`} />
            <Row label="Angebots-Prio" value={`${p.budget_sensitivity}/5`} />
            <Row label="Läden" value={p.selected_stores.join(', ') || '–'} />
            {p.allergies.length > 0 && <Row label="Allergien" value={p.allergies.join(', ')} />}
            {p.no_gos.length > 0 && <Row label="No-Gos" value={p.no_gos.join(', ')} />}
          </dl>
        )}
      </div>

      <div>
        <p className="mb-1.5 font-semibold text-stone-600">Gelernte Präferenzen</p>
        {!lp ? (
          <p className="text-stone-400">Noch keine Präferenzen</p>
        ) : (
          <dl className="space-y-1 text-stone-600">
            <Row label="Beliebt" value={lp.loved_dishes.join(', ') || '–'} />
            <Row label="Nicht gemocht" value={lp.disliked_dishes.join(', ') || '–'} />
            {Object.keys(lp.portion_adjustments).length > 0 && (
              <Row
                label="Portionen"
                value={Object.entries(lp.portion_adjustments).map(([k, v]) => `${k}: ${v}`).join(', ')}
              />
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
      <dt className="w-24 shrink-0 text-stone-400">{label}</dt>
      <dd className="break-words min-w-0">{value}</dd>
    </div>
  )
}
