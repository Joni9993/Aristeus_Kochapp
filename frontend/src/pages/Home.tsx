import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

type PlanSummary = {
  id: number
  week_start_date: string
  status: string
}

const PLAN_STATUS: Record<string, { label: string; cls: string }> = {
  pending: { label: 'Läuft…', cls: 'text-stone-400' },
  suggestions_ready: { label: 'Vorschläge bereit', cls: 'text-blue-600' },
  confirmed: { label: 'Aktiv', cls: 'text-emerald-700' },
  complete: { label: 'Abgeschlossen', cls: 'text-stone-400' },
}

function formatWeekRange(startIso: string): string {
  const start = new Date(startIso)
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  const fmt = (d: Date) => d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
  return `${fmt(start)} – ${fmt(end)}`
}

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

type OfferItem = {
  id: number
  product_name: string
  price_text: string | null
  quantity_text: string | null
  base_price: string | null
  hint: string | null
  category: string | null
  is_cooking_relevant: boolean
}

type StoreOffersResponse = {
  store: string
  label: string
  brochure_url: string
  valid_from: string | null
  valid_to: string | null
  total_count: number
  cooking_relevant_count: number
  offers: OfferItem[]
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

function groupByCategory(offers: OfferItem[]): Record<string, OfferItem[]> {
  const groups: Record<string, OfferItem[]> = {}
  for (const o of offers) {
    const key = o.category || 'Sonstige'
    if (!groups[key]) groups[key] = []
    groups[key].push(o)
  }
  return groups
}

function OffersDrawer({
  storeId,
  storeLabel,
  onClose,
}: {
  storeId: string
  storeLabel: string
  onClose: () => void
}) {
  const [data, setData] = useState<StoreOffersResponse | null>(null)
  const [cookingOnly, setCookingOnly] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    apiFetch<StoreOffersResponse>(`/stores/${storeId}/offers?cooking_only=${cookingOnly}`)
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Fehler beim Laden'))
      .finally(() => setLoading(false))
  }, [storeId, cookingOnly])

  const groups = data ? groupByCategory(data.offers) : {}
  const categoryKeys = Object.keys(groups).sort()

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30"
        onClick={onClose}
      />
      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-stone-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">{storeLabel} – Angebote</h2>
            {data && (
              <p className="mt-0.5 text-xs text-stone-500">
                Gültig {formatDate(data.valid_from)}–{formatDate(data.valid_to)}
                {' · '}
                {cookingOnly
                  ? `${data.cooking_relevant_count} Koch-Angebote`
                  : `${data.total_count} Angebote gesamt`}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="ml-4 rounded-md p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700"
            aria-label="Schließen"
          >
            ✕
          </button>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between border-b border-stone-100 px-5 py-2">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={cookingOnly}
              onChange={(e) => setCookingOnly(e.target.checked)}
              className="rounded"
            />
            Nur Koch-Angebote
          </label>
          {data && (
            <a
              href={data.brochure_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-emerald-700 underline hover:text-emerald-900"
            >
              Prospekt auf Kaufda →
            </a>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading && (
            <p className="text-center text-sm text-stone-400">Lädt…</p>
          )}
          {error && (
            <p className="text-center text-sm text-red-500">{error}</p>
          )}
          {!loading && !error && data && data.offers.length === 0 && (
            <p className="text-center text-sm text-stone-400">
              Keine Angebote gefunden.
            </p>
          )}
          {!loading && !error && categoryKeys.map((cat) => (
            <div key={cat} className="mb-5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">
                {cat}
              </h3>
              <div className="space-y-2">
                {groups[cat].map((offer) => (
                  <div
                    key={offer.id}
                    className="flex items-start justify-between rounded-lg border border-stone-100 bg-stone-50 px-3 py-2"
                  >
                    <div className="mr-3 flex-1">
                      <p className="text-sm font-medium leading-snug text-stone-800">
                        {offer.product_name}
                      </p>
                      {offer.quantity_text && (
                        <p className="mt-0.5 text-xs text-stone-500">{offer.quantity_text}</p>
                      )}
                      {offer.hint && (
                        <p className="mt-0.5 text-xs text-stone-400 italic">{offer.hint}</p>
                      )}
                    </div>
                    {offer.price_text && (
                      <div className="shrink-0 text-right">
                        <span className="text-base font-bold text-emerald-700">
                          {offer.price_text}
                        </span>
                        {offer.base_price && (
                          <p className="text-xs text-stone-400">{offer.base_price}</p>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

export default function Home() {
  const { household } = useAuth()
  const [freshness, setFreshness] = useState<FreshnessResponse | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMsg, setRefreshMsg] = useState('')
  const [plans, setPlans] = useState<PlanSummary[]>([])
  const [selectedStore, setSelectedStore] = useState<{ id: string; label: string } | null>(null)

  useEffect(() => {
    Promise.all([
      apiFetch<FreshnessResponse>('/stores/freshness'),
      apiFetch<PlanSummary[]>('/plans'),
    ]).then(([freshness, plans]) => {
      setFreshness(freshness)
      setPlans(plans)
      const needsRefresh = Object.values(freshness.stores).some(
        (s) => s.status === 'not_fetched' || s.status === 'outdated',
      )
      if (needsRefresh) {
        apiFetch('/stores/refresh', { method: 'POST' }).catch(() => {})
      }
    }).catch(() => {})
  }, [])

  async function handleRefresh() {
    setRefreshing(true)
    setRefreshMsg('')
    try {
      await apiFetch('/stores/refresh', { method: 'POST' })
      setRefreshMsg('Aktualisierung läuft im Hintergrund (dauert ~30–60 Sek.)…')
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
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Aristeus</h1>
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
          <div className="space-y-1">
            {stores.map(([storeId, s]) => {
              const cfg = STATUS_CONFIG[s.status]
              const hasOffers = s.offer_count > 0
              return (
                <button
                  key={storeId}
                  onClick={() => hasOffers && setSelectedStore({ id: storeId, label: s.label })}
                  disabled={!hasOffers}
                  className={`flex w-full items-center justify-between rounded-lg px-2 py-2 text-sm transition-colors ${
                    hasOffers
                      ? 'cursor-pointer hover:bg-stone-50 active:bg-stone-100'
                      : 'cursor-default'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${cfg.dot}`} />
                    <span className="font-medium">{s.label}</span>
                    <span className={`text-xs ${cfg.text}`}>{cfg.label}</span>
                  </div>
                  <div className="flex items-center gap-2 text-right text-xs text-stone-500">
                    {hasOffers ? (
                      <>
                        <span className="text-stone-700">{s.cooking_relevant_count ?? 0} Koch-Angebote</span>
                        {s.valid_from && s.valid_to && (
                          <span>{formatDate(s.valid_from)}–{formatDate(s.valid_to)}</span>
                        )}
                        <span className="text-stone-400">›</span>
                      </>
                    ) : (
                      <span>–</span>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </section>

      {/* Letzte Pläne */}
      {plans.length > 0 && (
        <section className="mb-6 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 font-semibold">Letzte Pläne</h2>
          <div className="space-y-1">
            {plans.slice(0, 10).map((p) => {
              const st = PLAN_STATUS[p.status] ?? { label: p.status, cls: 'text-stone-400' }
              return (
                <div key={p.id} className="flex items-center rounded-lg px-2 py-2 hover:bg-stone-50">
                  <Link
                    to={`/plan/${p.id}`}
                    className="flex flex-1 items-center justify-between"
                  >
                    <span className="text-sm font-medium text-stone-700">{formatWeekRange(p.week_start_date)}</span>
                    <span className={`text-xs ${st.cls}`}>{st.label}</span>
                  </Link>
                  <button
                    onClick={async (e) => {
                      e.preventDefault()
                      if (!confirm('Plan löschen?')) return
                      await apiFetch(`/plans/${p.id}`, { method: 'DELETE' }).catch(() => {})
                      setPlans((prev) => prev.filter((x) => x.id !== p.id))
                    }}
                    className="ml-2 shrink-0 opacity-30 hover:opacity-100 active:opacity-100"
                    title="Plan löschen"
                  >
                    🗑
                  </button>
                </div>
              )
            })}
          </div>
        </section>
      )}

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

      {/* Offers drawer */}
      {selectedStore && (
        <OffersDrawer
          storeId={selectedStore.id}
          storeLabel={selectedStore.label}
          onClose={() => setSelectedStore(null)}
        />
      )}
    </main>
  )
}
