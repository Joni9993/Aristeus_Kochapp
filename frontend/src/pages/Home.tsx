import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

type StoreStatus = {
  label: string
  status: 'fresh' | 'stale' | 'outdated' | 'not_fetched'
  offer_count: number
  cooking_relevant_count?: number
  fetched_at: string | null
  valid_from: string | null
  valid_to: string | null
}

type FreshnessResponse = {
  plz: string
  stores: Record<string, StoreStatus>
}

const STATUS_CONFIG = {
  fresh: { dot: 'bg-emerald-500', text: 'text-emerald-700', label: 'Aktuell' },
  stale: { dot: 'bg-amber-400', text: 'text-amber-700', label: 'Veraltet' },
  outdated: { dot: 'bg-red-400', text: 'text-red-700', label: 'Sehr alt' },
  not_fetched: { dot: 'bg-stone-300', text: 'text-stone-500', label: 'Noch nicht geladen' },
}

function formatDate(iso: string | null): string {
  if (!iso) return '–'
  const d = new Date(iso)
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
}

export default function Home() {
  const { household, refresh } = useAuth()
  const navigate = useNavigate()
  const [freshness, setFreshness] = useState<FreshnessResponse | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMsg, setRefreshMsg] = useState('')

  useEffect(() => {
    apiFetch<FreshnessResponse>('/stores/freshness')
      .then(setFreshness)
      .catch(() => {})
  }, [])

  async function handleLogout() {
    await apiFetch('/auth/logout', { method: 'POST' })
    await refresh()
    navigate('/login', { replace: true })
  }

  async function handleRefresh() {
    setRefreshing(true)
    setRefreshMsg('')
    try {
      await apiFetch('/stores/refresh', { method: 'POST' })
      setRefreshMsg('Aktualisierung läuft im Hintergrund (dauert ~30–60 Sek.)…')
      // Re-fetch freshness after a delay
      setTimeout(() => {
        apiFetch<FreshnessResponse>('/stores/freshness').then(setFreshness).catch(() => {})
        setRefreshMsg('')
      }, 45000)
    } catch (err) {
      setRefreshMsg(err instanceof ApiError ? err.message : 'Fehler beim Refresh')
    } finally {
      setRefreshing(false)
    }
  }

  const stores = freshness ? Object.entries(freshness.stores) : []
  const hasAnyOffers = stores.some(([, s]) => s.offer_count > 0)

  return (
    <main className="mx-auto max-w-xl p-6">
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Aristeus</h1>
        <div className="flex items-center gap-3">
          {household?.is_admin && (
            <Link to="/admin" className="text-sm text-stone-500 underline hover:text-stone-700">Admin</Link>
          )}
          <Link to="/profile" className="text-sm text-stone-500 underline hover:text-stone-700">Profil</Link>
          <button onClick={handleLogout} className="text-sm text-stone-500 underline hover:text-stone-700">Abmelden</button>
        </div>
      </header>

      {/* Angebots-Freshness */}
      <section className="mb-6 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">
            Angebote {freshness ? `(PLZ ${freshness.plz})` : ''}
          </h2>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="rounded-lg border border-stone-300 px-3 py-1 text-xs hover:bg-stone-50 disabled:opacity-50"
          >
            {refreshing ? 'Läuft…' : 'Aktualisieren'}
          </button>
        </div>

        {refreshMsg && <p className="mb-2 text-xs text-amber-600">{refreshMsg}</p>}

        {stores.length === 0 ? (
          <p className="text-sm text-stone-400">Keine Läden konfiguriert oder noch nicht geladen.</p>
        ) : (
          <div className="space-y-2">
            {stores.map(([storeId, s]) => {
              const cfg = STATUS_CONFIG[s.status]
              return (
                <div key={storeId} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${cfg.dot}`} />
                    <span className="font-medium">{s.label}</span>
                    <span className={`text-xs ${cfg.text}`}>{cfg.label}</span>
                  </div>
                  <div className="text-right text-xs text-stone-500">
                    {s.offer_count > 0 ? (
                      <>
                        <span className="text-stone-700">{s.cooking_relevant_count ?? 0} Koch-Angebote</span>
                        {s.valid_from && s.valid_to && (
                          <span className="ml-2">{formatDate(s.valid_from)}–{formatDate(s.valid_to)}</span>
                        )}
                      </>
                    ) : (
                      <span>–</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {/* Wochenplan-CTA */}
      <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 text-center">
        <p className="font-medium text-emerald-800">
          Willkommen{household?.username ? `, ${household.username}` : ''}!
        </p>
        {hasAnyOffers ? (
          <>
            <p className="mt-1 text-sm text-emerald-700">
              Angebote aus deiner Region sind geladen.
            </p>
            <Link
              to="/plan/new"
              className="mt-4 block w-full rounded-lg bg-emerald-600 px-4 py-2 text-center text-sm font-medium text-white hover:bg-emerald-700"
            >
              Neue Woche planen
            </Link>
          </>
        ) : (
          <>
            <p className="mt-1 text-sm text-emerald-700">
              Lade zuerst die Angebote für deine Region — klicke auf „Aktualisieren".
            </p>
            <p className="mt-1 text-xs text-emerald-600">
              Der erste Lauf dauert ~30–60 Sekunden.
            </p>
          </>
        )}
      </section>

    </main>
  )
}
