import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import DishImage from '../components/DishImage'
import Laurel from '../components/Laurel'
import { DAYS, germanWeekdayName } from '../types'
import { APP_VERSION } from '../version'
import type { Dish, Plan } from '../types'

type PlanSummary = {
  id: number
  week_start_date: string
  status: string
}

type TodayInfo = {
  planId: number
  dish: Dish | null
  upcoming: Dish[]
  savings: Plan['savings'] | null
}

const PLAN_STATUS: Record<string, { label: string; cls: string }> = {
  pending: { label: 'Läuft…', cls: 'text-muted' },
  suggestions_ready: { label: 'Vorschläge bereit', cls: 'text-indigo-600 dark:text-indigo-400' },
  confirmed: { label: 'Aktiv', cls: 'text-olive' },
  complete: { label: 'Abgeschlossen', cls: 'text-muted' },
}

function formatWeekRange(startIso: string): string {
  const start = new Date(startIso)
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  const fmt = (d: Date) => d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
  return `${fmt(start)} – ${fmt(end)}`
}

function isCurrentWeek(startIso: string): boolean {
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const start = new Date(startIso + 'T00:00:00')
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  return now >= start && now <= end
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

// Freshness status dots — a functional traffic-light, not the honey/offers
// accent (honey is reserved for offer badges, savings and favorite stars).
const STATUS_CONFIG: Record<StoreStatus['status'], { dot: string; label: string }> = {
  fresh: { dot: 'bg-olive', label: 'Aktuell' },
  stale: { dot: 'bg-amber-400 dark:bg-amber-500', label: 'Veraltet' },
  outdated: { dot: 'bg-red-400 dark:bg-red-500', label: 'Sehr alt' },
  not_fetched: { dot: 'bg-line', label: 'Noch nicht geladen' },
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
        className="fixed inset-0 z-40 bg-ink/30"
        onClick={onClose}
      />
      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate font-display text-lg font-semibold text-ink">{storeLabel} – Angebote</h2>
            {data && (
              <p className="mt-0.5 text-xs text-muted">
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
            className="shrink-0 rounded-md p-2 text-muted hover:bg-surface hover:text-ink"
            aria-label="Schließen"
          >
            ✕
          </button>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between border-b border-line px-5 py-2">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-ink/75">
            <input
              type="checkbox"
              checked={cookingOnly}
              onChange={(e) => setCookingOnly(e.target.checked)}
              className="rounded accent-olive"
            />
            Nur Koch-Angebote
          </label>
          {data && (
            <a
              href={data.brochure_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-olive underline hover:text-olive-hover"
            >
              Prospekt auf Kaufda →
            </a>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading && (
            <p className="text-center text-sm text-muted">Lädt…</p>
          )}
          {error && (
            <p className="text-center text-sm text-red-500 dark:text-red-400">{error}</p>
          )}
          {!loading && !error && data && data.offers.length === 0 && (
            <p className="text-center text-sm text-muted">
              Keine Angebote gefunden.
            </p>
          )}
          {!loading && !error && categoryKeys.map((cat) => (
            <div key={cat} className="mb-5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                {cat}
              </h3>
              <div className="space-y-2">
                {groups[cat].map((offer) => (
                  <div
                    key={offer.id}
                    className="flex items-start justify-between rounded-lg border border-line bg-surface px-3 py-2"
                  >
                    <div className="mr-3 min-w-0 flex-1">
                      <p className="text-sm font-medium leading-snug text-ink">
                        {offer.product_name}
                      </p>
                      {offer.quantity_text && (
                        <p className="mt-0.5 text-xs text-muted">{offer.quantity_text}</p>
                      )}
                      {offer.hint && (
                        <p className="mt-0.5 text-xs text-muted italic">{offer.hint}</p>
                      )}
                    </div>
                    {offer.price_text && (
                      <div className="shrink-0 text-right">
                        <span className="text-base font-bold text-honey">
                          {offer.price_text}
                        </span>
                        {offer.base_price && (
                          <p className="text-xs text-muted">{offer.base_price}</p>
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

// ---------------------------------------------------------------------------
// "Heute" hero — the single most important thing on the page. Three states:
// today's confirmed dish (photo hero), an active plan with nothing cooking
// today, or no plan for the current week at all (CTA).
// ---------------------------------------------------------------------------

function TodayHero({
  todayInfo,
  currentWeekPlan,
}: {
  todayInfo: TodayInfo | null
  currentWeekPlan: PlanSummary | null
}) {
  const todayName = germanWeekdayName(new Date())

  if (todayInfo?.dish) {
    const { dish, planId } = todayInfo
    return (
      <Link
        to={`/plan/${planId}?dish=${dish.id}`}
        className="relative mb-3 block h-40 overflow-hidden rounded-2xl shadow-sm"
      >
        <DishImage
          imageUrl={dish.image_url}
          name={dish.name}
          cuisine={dish.cuisine}
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-ink/85 via-ink/25 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-white/80">
            Heute · {todayName}
          </p>
          <p className="mt-1 line-clamp-2 font-display text-xl font-semibold leading-tight text-white">
            {dish.name}
          </p>
          {dish.cook_time_min && (
            <p className="mt-1 text-xs text-white/80">{dish.cook_time_min} Min.</p>
          )}
        </div>
      </Link>
    )
  }

  if (todayInfo) {
    const { upcoming, planId } = todayInfo
    return (
      <Link
        to={`/plan/${planId}`}
        className="mb-3 block rounded-2xl border border-line bg-card px-4 py-3.5 hover:bg-surface"
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Heute · {todayName}</p>
        <p className="mt-1 text-sm text-ink/75 line-clamp-2">
          {upcoming.length > 0
            ? `Nichts geplant — als Nächstes: ${upcoming.map((d) => `${d.cook_day}: ${d.name}`).join(' · ')}`
            : 'Heute ist nichts geplant.'}
        </p>
      </Link>
    )
  }

  if (currentWeekPlan) {
    const st = PLAN_STATUS[currentWeekPlan.status]
    const label =
      currentWeekPlan.status === 'suggestions_ready'
        ? 'Vorschläge bereit — jetzt auswählen'
        : currentWeekPlan.status === 'error'
          ? 'Fehler bei der Planung — erneut versuchen'
          : 'Vorschläge werden erstellt…'
    return (
      <Link
        to={`/plan/${currentWeekPlan.id}`}
        className="mb-3 block rounded-2xl border border-line bg-card px-4 py-3.5 hover:bg-surface"
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Heute · {todayName}</p>
        <p className={`mt-1 text-sm font-medium ${st?.cls ?? 'text-ink/75'}`}>{label}</p>
      </Link>
    )
  }

  return (
    <Link
      to="/plan/new"
      className="mb-3 flex flex-col items-center justify-center gap-1 rounded-2xl border border-line bg-card px-4 py-6 text-center hover:bg-surface"
    >
      <span className="font-display text-lg font-semibold text-ink">Noch kein Plan für diese Woche</span>
      <span className="text-sm font-medium text-olive">Neue Woche planen →</span>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Quick-link tile row
// ---------------------------------------------------------------------------

function QuickTile({ to, label, icon }: { to: string; label: string; icon: React.ReactNode }) {
  return (
    <Link
      to={to}
      className="flex flex-col items-center justify-center gap-1.5 rounded-2xl border border-line bg-card py-3.5 text-center hover:bg-surface active:bg-surface"
    >
      <span className="text-olive">{icon}</span>
      <span className="text-xs font-medium text-ink">{label}</span>
    </Link>
  )
}

function CalendarIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-6 w-6">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
    </svg>
  )
}

function CartIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-6 w-6">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 0 0-3 3h15.75m-12.75-3h11.218c1.121-2.3 1.972-4.688 2.545-7.153.126-.541-.298-1.047-.854-1.047H5.106M7.5 14.25 5.106 5.272M6 20.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm12.75 0a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z" />
    </svg>
  )
}

function BookIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-6 w-6">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
    </svg>
  )
}

function RefreshIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor" className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Main page — everything above the "Frühere Wochen" accordion is designed to
// fit a ~360×740 viewport without scrolling.
// ---------------------------------------------------------------------------

export default function Home() {
  const [freshness, setFreshness] = useState<FreshnessResponse | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMsg, setRefreshMsg] = useState('')
  const [plans, setPlans] = useState<PlanSummary[]>([])
  const [selectedStore, setSelectedStore] = useState<{ id: string; label: string } | null>(null)
  const [todayInfo, setTodayInfo] = useState<TodayInfo | null>(null)
  const [feedbackPlan, setFeedbackPlan] = useState<Plan | null>(null)
  const [feedbackDismissed, setFeedbackDismissed] = useState(false)

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

      // "Heute" card: find the plan whose cook week contains today.
      const now = new Date()
      now.setHours(0, 0, 0, 0)
      const candidate = plans.find((p) => {
        if (p.status !== 'confirmed' && p.status !== 'complete') return false
        const start = new Date(p.week_start_date + 'T00:00:00')
        const end = new Date(start)
        end.setDate(end.getDate() + 6)
        return now >= start && now <= end
      })
      if (candidate) {
        apiFetch<Plan>(`/plans/${candidate.id}`).then((full) => {
          const weekday = germanWeekdayName(now)
          const todayIdx = DAYS.indexOf(weekday)
          const confirmedDishes = (full.dishes || []).filter((d) => d.dish_status === 'confirmed')
          const dish = confirmedDishes.find((d) => d.cook_day === weekday) || null
          const upcoming = confirmedDishes
            .filter((d) => d.cook_day && DAYS.indexOf(d.cook_day) > todayIdx)
            .sort((a, b) => DAYS.indexOf(a.cook_day!) - DAYS.indexOf(b.cook_day!))
            .slice(0, 2)
          setTodayInfo({ planId: full.id, dish, upcoming, savings: full.savings ?? null })
        }).catch(() => {})
      }
    }).catch(() => {})

    apiFetch<{ plan: Plan | null }>('/plans/feedback-pending')
      .then((r) => setFeedbackPlan(r.plan))
      .catch(() => {})
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

  const currentWeekPlan = plans.find((p) => isCurrentWeek(p.week_start_date)) || null
  const planTileTarget = currentWeekPlan ? `/plan/${currentWeekPlan.id}` : '/plan/new'

  const pendingCount = feedbackPlan
    ? (feedbackPlan.dishes || []).filter(
        (d) => d.dish_status === 'confirmed' && d.feedback_thumbs === null
      ).length
    : 0

  return (
    <main className="mx-auto max-w-xl px-4 py-4 sm:p-6">
      {/* a) Compact header */}
      <header className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Laurel className="h-4 w-4 shrink-0 -scale-x-100 text-olive" />
          <h1 className="font-display text-xl font-semibold tracking-tight text-ink">Aristeus</h1>
        </div>
        <span className="text-xs text-muted">v{APP_VERSION}</span>
      </header>

      {/* b) Feedback pending — single compact row */}
      {feedbackPlan && !feedbackDismissed && (
        <div className="mb-3 flex min-h-11 items-center gap-1 rounded-xl border border-honey/40 bg-honey-soft pl-3.5 pr-1.5 py-1.5 text-sm">
          <Link to={`/plan/${feedbackPlan.id}/feedback`} className="flex min-w-0 flex-1 items-center gap-2">
            <span className="min-w-0 truncate font-medium text-ink">
              Wie war eure Woche? {pendingCount} {pendingCount === 1 ? 'Gericht offen' : 'Gerichte offen'}
            </span>
            <span className="shrink-0 text-olive">→</span>
          </Link>
          <button
            onClick={() => setFeedbackDismissed(true)}
            aria-label="Ausblenden"
            className="shrink-0 p-2 text-ink/50 hover:text-ink"
          >
            ✕
          </button>
        </div>
      )}

      {/* c) Heute-Hero */}
      <TodayHero todayInfo={todayInfo} currentWeekPlan={currentWeekPlan} />

      {/* d) Quick-link tiles */}
      <div className="mb-3 grid grid-cols-3 gap-2">
        <QuickTile to={planTileTarget} label="Wochenplan" icon={<CalendarIcon />} />
        <QuickTile to="/shopping" label="Einkauf" icon={<CartIcon />} />
        <QuickTile to="/cookbook" label="Rezepte" icon={<BookIcon />} />
      </div>

      {/* e) Angebote — compact single card, horizontal store chips */}
      <section className="mb-3 rounded-2xl border border-line bg-card p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="min-w-0 truncate text-xs font-semibold uppercase tracking-wide text-muted">
            Angebote{freshness ? ` · PLZ ${freshness.plz}` : ''}
          </p>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            aria-label="Angebote aktualisieren"
            className="shrink-0 rounded-full p-1.5 text-muted hover:bg-surface hover:text-ink disabled:opacity-50"
          >
            <RefreshIcon className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {refreshMsg && <p className="mb-2 text-xs text-olive">{refreshMsg}</p>}

        {stores.length === 0 ? (
          <p className="text-xs text-muted">Keine Läden konfiguriert oder noch nicht geladen.</p>
        ) : (
          <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-0.5">
            {stores.map(([storeId, s]) => {
              const cfg = STATUS_CONFIG[s.status]
              const hasOffers = s.offer_count > 0
              return (
                <button
                  key={storeId}
                  onClick={() => hasOffers && setSelectedStore({ id: storeId, label: s.label })}
                  disabled={!hasOffers}
                  className={`flex min-h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors ${
                    hasOffers
                      ? 'border-line hover:bg-surface active:bg-surface'
                      : 'border-line/60 opacity-50'
                  }`}
                >
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${cfg.dot}`} />
                  <span className="font-medium text-ink">{s.label}</span>
                  {hasOffers && (
                    <span className="text-muted">{s.cooking_relevant_count ?? 0}</span>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </section>

      {/* e2) Ersparnis dieser Woche — honey banner, only when the current
          week's plan actually uses offers */}
      {todayInfo?.savings && todayInfo.savings.offers_used > 0 && (
        <Link
          to={`/plan/${todayInfo.planId}`}
          className="mb-3 flex min-h-11 items-center gap-2 rounded-xl border border-honey/40 bg-honey-soft px-3.5 py-2.5 text-sm"
        >
          <span aria-hidden>🏷️</span>
          <span className="min-w-0 flex-1 font-medium text-ink">
            {todayInfo.savings.estimated_savings > 0
              ? `Ca. ${todayInfo.savings.estimated_savings.toLocaleString('de-DE', {
                  style: 'currency',
                  currency: 'EUR',
                })} gespart diese Woche durch Angebote`
              : `${todayInfo.savings.offers_used} Zutaten diese Woche im Angebot`}
          </span>
          <span className="shrink-0 text-honey">→</span>
        </Link>
      )}

      {/* f) Frühere Wochen — collapsed, doesn't count toward the viewport goal */}
      {plans.length > 0 && (
        <details className="rounded-2xl border border-line bg-card">
          <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-ink/75">
            Frühere Wochen
          </summary>
          <div className="space-y-1 px-2 pb-2">
            {plans.slice(0, 10).map((p) => {
              const st = PLAN_STATUS[p.status] ?? { label: p.status, cls: 'text-muted' }
              return (
                <div key={p.id} className="flex min-h-11 items-center gap-2 rounded-lg px-2 py-2 hover:bg-surface">
                  <Link
                    to={`/plan/${p.id}`}
                    className="flex min-w-0 flex-1 items-center justify-between gap-2"
                  >
                    <span className="shrink-0 text-sm font-medium text-ink/75">{formatWeekRange(p.week_start_date)}</span>
                    <span className={`shrink-0 truncate text-xs ${st.cls}`}>{st.label}</span>
                  </Link>
                  <button
                    onClick={async (e) => {
                      e.preventDefault()
                      if (!confirm('Plan löschen?')) return
                      await apiFetch(`/plans/${p.id}`, { method: 'DELETE' }).catch(() => {})
                      setPlans((prev) => prev.filter((x) => x.id !== p.id))
                    }}
                    className="shrink-0 p-2 opacity-30 hover:opacity-100 active:opacity-100"
                    title="Plan löschen"
                  >
                    🗑
                  </button>
                </div>
              )
            })}
          </div>
        </details>
      )}

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
