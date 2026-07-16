import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import DishImage from '../components/DishImage'
import FeedbackRow from '../components/FeedbackRow'
import RecipeDetails from '../components/RecipeDetails'
import ShoppingView from '../components/ShoppingView'
import { cuisineBadgeClass, DAYS, germanWeekdayName } from '../types'
import type { Dish, Plan, Savings, ShoppingItem } from '../types'

const EUR = { style: 'currency', currency: 'EUR' } as const

function formatSavingsBanner(savings: Savings): string {
  if (savings.estimated_savings > 0) {
    return `ca. ${savings.estimated_savings.toLocaleString('de-DE', EUR)} gespart durch ${savings.offers_used} Angebote`
  }
  return `${savings.offers_used} Zutaten im Angebot (${savings.offer_total.toLocaleString('de-DE', EUR)} Aktionspreise)`
}

// ---------------------------------------------------------------------------
// Pending view
// ---------------------------------------------------------------------------

function PendingView({
  onRefresh,
  message = 'Gerichte werden vorgeschlagen…',
}: {
  onRefresh: () => void
  message?: string
}) {
  const [elapsed, setElapsed] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    const poll = setInterval(onRefresh, 3000)
    const tick = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => { clearInterval(poll); clearInterval(tick) }
  }, [onRefresh])

  return (
    <div className="flex flex-col items-center gap-4 py-12 text-muted">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-olive border-t-transparent" />
      <p className="text-sm">{message}</p>
      <p className="text-xs text-muted">
        {elapsed < 90 ? 'Das dauert ca. 10–30 Sekunden' : `${elapsed}s — dauert ungewöhnlich lang`}
      </p>
      {elapsed >= 120 && (
        <button
          onClick={() => navigate('/plan/new')}
          className="mt-2 rounded-lg border border-line px-4 py-2 text-xs text-ink/75 hover:bg-surface"
        >
          Neu versuchen
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Dish card (suggestion mode)
// ---------------------------------------------------------------------------

type Selection = { checked: boolean; cook_day: string }

function DishCard({
  dish,
  sel,
  onChange,
}: {
  dish: Dish
  sel: Selection
  onChange: (s: Selection) => void
}) {
  const color = cuisineBadgeClass(dish.cuisine)

  return (
    <div
      className={`rounded-xl border overflow-hidden transition-all ${
        sel.checked ? 'border-olive bg-olive-soft' : 'border-line bg-card'
      }`}
    >
      <DishImage imageUrl={dish.image_url} name={dish.name} cuisine={dish.cuisine} className="h-36" />
      <label className="flex cursor-pointer items-start gap-3 p-4">
        <input
          type="checkbox"
          checked={sel.checked}
          onChange={(e) => onChange({ ...sel, checked: e.target.checked })}
          className="mt-1 h-5 w-5 shrink-0 accent-olive"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="break-words font-display font-semibold text-ink leading-tight">{dish.name}</span>
            {dish.cuisine && (
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
                {dish.cuisine}
              </span>
            )}
            {dish.cook_time_min && (
              <span className="shrink-0 text-xs text-muted">{dish.cook_time_min} Min.</span>
            )}
          </div>
          {dish.description && (
            <p className="text-sm text-muted leading-snug">{dish.description}</p>
          )}
        </div>
      </label>

      {sel.checked && (
        <div className="px-4 pb-4">
          <label className="mb-1 block text-xs text-muted">Wochentag</label>
          <select
            value={sel.cook_day}
            onChange={(e) => onChange({ ...sel, cook_day: e.target.value })}
            className="w-full rounded-lg border border-line px-2 py-2"
          >
            <option value="">— Tag wählen —</option>
            {DAYS.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Suggestions view
// ---------------------------------------------------------------------------

function SuggestionsView({
  plan,
  onConfirmed,
  onReload,
}: {
  plan: Plan
  onConfirmed: (updated: Plan) => void
  onReload: () => void
}) {
  const dishes = (plan.dishes || []).filter((d) => d.dish_status === 'suggestion')
  const [selections, setSelections] = useState<Record<number, Selection>>(() =>
    Object.fromEntries(dishes.map((d) => [d.id, { checked: false, cook_day: '' }]))
  )
  const [loadingMore, setLoadingMore] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Sync when dishes change (after +5 more)
  useEffect(() => {
    setSelections((prev) => {
      const next = { ...prev }
      for (const d of dishes) {
        if (!(d.id in next)) next[d.id] = { checked: false, cook_day: '' }
      }
      return next
    })
  }, [dishes.length])

  // Clean up any running poll on unmount (e.g. plan gets confirmed/navigated away).
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const selected = dishes.filter((d) => selections[d.id]?.checked)

  async function handleMoreSuggestions() {
    setLoadingMore(true)
    setError('')
    const startCount = dishes.length
    try {
      await apiFetch(`/plans/${plan.id}/more-suggestions`, { method: 'POST' })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler')
      setLoadingMore(false)
      return
    }

    const startedAt = Date.now()
    pollRef.current = setInterval(async () => {
      try {
        const updated = await apiFetch<Plan>(`/plans/${plan.id}`)
        const newCount = (updated.dishes || []).filter((d) => d.dish_status === 'suggestion').length
        if (newCount > startCount) {
          if (pollRef.current) clearInterval(pollRef.current)
          pollRef.current = null
          setLoadingMore(false)
          onReload()
          return
        }
      } catch {
        // transient error — keep polling until timeout
      }
      if (Date.now() - startedAt > 120000) {
        if (pollRef.current) clearInterval(pollRef.current)
        pollRef.current = null
        setLoadingMore(false)
        setError('Dauert ungewöhnlich lange — später erneut versuchen.')
      }
    }, 3000)
  }

  async function handleConfirm() {
    if (selected.length === 0) {
      setError('Wähle mindestens ein Gericht aus.')
      return
    }
    setConfirming(true)
    setError('')
    try {
      const sels = selected.map((d) => ({
        dish_id: d.id,
        cook_day: selections[d.id]?.cook_day || null,
      }))
      const updated = await apiFetch<Plan>(`/plans/${plan.id}/confirm`, {
        method: 'POST',
        body: { selections: sels },
      })
      onConfirmed(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler beim Bestätigen')
      setConfirming(false)
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display font-semibold text-ink">Gerichtsvorschläge</h2>
        <span className="text-xs text-muted">{selected.length} ausgewählt</span>
      </div>

      {error && <p className="mb-3 rounded bg-red-50 dark:bg-red-950/40 p-3 text-sm text-red-700 dark:text-red-300">{error}</p>}

      <div className="space-y-3 mb-4">
        {dishes.map((d) => (
          <DishCard
            key={d.id}
            dish={d}
            sel={selections[d.id] || { checked: false, cook_day: '' }}
            onChange={(s) => setSelections((prev) => ({ ...prev, [d.id]: s }))}
          />
        ))}
      </div>

      {dishes.length < 30 && (
        <button
          onClick={handleMoreSuggestions}
          disabled={loadingMore}
          className="mb-4 w-full rounded-lg border border-line py-2 text-sm text-ink/75 hover:bg-surface disabled:opacity-50"
        >
          {loadingMore ? 'Lädt…' : '+ 5 weitere Vorschläge'}
        </button>
      )}

      {/* Sticky so the confirm action stays reachable after scrolling past many cards. */}
      <div
        className="sticky z-20 -mx-4 border-t border-line bg-card/90 px-4 pt-3 backdrop-blur sm:-mx-6 sm:px-6"
        style={{ bottom: 'calc(6rem + env(safe-area-inset-bottom))', paddingBottom: '0.75rem' }}
      >
        <button
          onClick={handleConfirm}
          disabled={confirming || selected.length === 0}
          className="w-full rounded-lg bg-olive py-3 text-sm font-semibold text-olive-on hover:bg-olive-hover disabled:opacity-50"
        >
          {confirming ? 'Rezepte werden generiert…' : `${selected.length} Gerichte übernehmen`}
        </button>
        {confirming && (
          <p className="mt-2 text-center text-xs text-muted">Dauert ca. 30–60 Sekunden…</p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Recipes view
// ---------------------------------------------------------------------------

function RecipesView({
  plan,
  onReload,
  initialOpenDishId,
}: {
  plan: Plan
  onReload: () => void
  initialOpenDishId?: number | null
}) {
  const [open, setOpen] = useState<number | null>(null)
  const [cookModeDish, setCookModeDish] = useState<Dish | null>(null)
  const itemRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const appliedInitialOpen = useRef(false)
  const confirmed = (plan.dishes || []).filter((d) => d.dish_status === 'confirmed')
  const flexible = confirmed.filter((d) => !d.cook_day)
  const todayName = germanWeekdayName(new Date())

  function openDish(id: number) {
    setOpen(id)
    requestAnimationFrame(() => {
      itemRefs.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  // Deep link from Home's "Heute"-card (/plan/:id?dish=:dishId) — open that
  // dish's accordion once the confirmed dishes are available.
  useEffect(() => {
    if (appliedInitialOpen.current || !initialOpenDishId) return
    if (confirmed.some((d) => d.id === initialOpenDishId)) {
      appliedInitialOpen.current = true
      openDish(initialOpenDishId)
    }
  }, [initialOpenDishId, confirmed])

  async function handleRegenerateRecipe(dish: Dish) {
    // Kicks off a background retry (plan briefly flips to 'confirming' — the
    // page's own PendingView + polling picks that up).
    try {
      await apiFetch(`/plans/${plan.id}/dishes/${dish.id}/regenerate-recipe`, { method: 'POST' })
    } catch {
      // ignore — reload shows current state either way
    }
    onReload()
  }

  return (
    <div>
      <h2 className="mb-4 font-display font-semibold text-ink">Rezepte</h2>

      {/* Wochenkalender — compact day chips (Mo–So) with a dot for occupied
          days, plus a vertical list of "Tag · Gericht" rows below. A 7-column
          grid is too narrow to hold dish names on a 360px phone, so the two
          are split. */}
      <div className="mb-3 flex justify-between gap-1">
        {DAYS.map((day) => {
          const dish = confirmed.find((d) => d.cook_day === day)
          const isToday = day === todayName
          return (
            <div key={day} className="flex flex-1 flex-col items-center gap-1">
              <span
                className={`flex h-8 w-8 items-center justify-center rounded-full text-[11px] font-semibold ${
                  isToday
                    ? 'bg-olive text-olive-on'
                    : dish
                      ? 'bg-olive-soft text-olive'
                      : 'bg-line/50 text-muted'
                }`}
              >
                {day.slice(0, 2)}
              </span>
              <span className={`h-1.5 w-1.5 rounded-full ${dish ? 'bg-olive' : 'bg-transparent'}`} />
            </div>
          )
        })}
      </div>

      <div className="mb-4 space-y-1">
        {DAYS.filter((day) => confirmed.some((d) => d.cook_day === day)).map((day) => {
          const dish = confirmed.find((d) => d.cook_day === day)!
          const isToday = day === todayName
          return (
            <button
              key={day}
              onClick={() => openDish(dish.id)}
              className={`flex w-full min-w-0 items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-olive-soft ${
                isToday ? 'bg-olive-soft' : ''
              }`}
            >
              <span className={`shrink-0 text-xs font-semibold ${isToday ? 'text-olive' : 'text-muted'}`}>
                {day.slice(0, 2)}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-ink">{dish.name}</span>
            </button>
          )
        })}
      </div>

      {flexible.length > 0 && (
        <div className="mb-4 rounded-lg bg-surface px-3 py-2 text-xs text-muted">
          <span className="font-semibold">Flexibel: </span>
          {flexible.map((d, i) => (
            <span key={d.id}>
              <button onClick={() => openDish(d.id)} className="underline hover:text-olive">
                {d.name}
              </button>
              {i < flexible.length - 1 ? ', ' : ''}
            </span>
          ))}
        </div>
      )}
      {flexible.length === 0 && <div className="mb-4" />}

      <div className="space-y-2">
        {confirmed.map((d) => (
          <div
            key={d.id}
            ref={(el) => { itemRefs.current[d.id] = el }}
            className="rounded-xl border border-line overflow-hidden"
          >
            <button
              className="flex w-full min-w-0 items-center justify-between gap-2 p-4 text-left hover:bg-surface"
              onClick={() => setOpen(open === d.id ? null : d.id)}
            >
              <div className="flex min-w-0 flex-1 items-baseline gap-2">
                <span className="truncate font-display font-medium text-ink">{d.name}</span>
                {d.cook_day && (
                  <span className="shrink-0 text-xs text-muted">{d.cook_day}</span>
                )}
              </div>
              <span className="shrink-0 text-muted">{open === d.id ? '▲' : '▼'}</span>
            </button>

            {open === d.id && d.recipe && (
              <div className="border-t border-line text-sm">
                <DishImage imageUrl={d.image_url} name={d.name} cuisine={d.cuisine} className="h-48" />
                <div className="p-4">
                <RecipeDetails
                  recipe={d.recipe}
                  zutatenAction={
                    <button
                      onClick={() => setCookModeDish(d)}
                      className="rounded-lg border border-olive/50 px-3 py-2 text-xs font-medium text-olive hover:bg-olive-soft"
                    >
                      👨‍🍳 Kochmodus
                    </button>
                  }
                />

                <div className="mt-4 border-t border-line pt-3">
                  <FeedbackRow planId={plan.id} dish={d} />
                </div>
                </div>
              </div>
            )}
            {open === d.id && !d.recipe && (
              <div className="border-t border-line p-4 text-sm text-muted">
                <p className="mb-2">Kein Rezept verfügbar.</p>
                <button
                  onClick={() => handleRegenerateRecipe(d)}
                  className="min-h-11 rounded-lg border border-olive/50 px-3 py-2 text-xs font-medium text-olive hover:bg-olive-soft"
                >
                  Rezept jetzt generieren
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {cookModeDish && (
        <CookMode dish={cookModeDish} onClose={() => setCookModeDish(null)} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Cook mode (fullscreen, wake-lock enabled step-by-step view)
// ---------------------------------------------------------------------------

function CookMode({ dish, onClose }: { dish: Dish; onClose: () => void }) {
  const [step, setStep] = useState(0)
  const wakeLockRef = useRef<WakeLockSentinel | null>(null)

  useEffect(() => {
    async function acquire() {
      try {
        if ('wakeLock' in navigator) {
          wakeLockRef.current = await navigator.wakeLock.request('screen')
        }
      } catch {
        // unsupported or denied — cooking mode still works without it
      }
    }
    acquire()

    function handleVisibility() {
      if (document.visibilityState === 'visible' && !wakeLockRef.current) {
        acquire()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility)
      wakeLockRef.current?.release().catch(() => {})
      wakeLockRef.current = null
    }
  }, [])

  const steps = dish.recipe?.schritte || []
  if (!dish.recipe) return null

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-surface">
      <div
        className="flex min-w-0 items-center justify-between gap-2 border-b border-line bg-card px-4 py-3"
        style={{ paddingTop: 'max(0.75rem, env(safe-area-inset-top))' }}
      >
        <span className="min-w-0 flex-1 truncate font-display font-semibold text-ink">{dish.name}</span>
        <button
          onClick={onClose}
          className="shrink-0 p-2 text-xl leading-none text-muted hover:text-ink"
          aria-label="Schließen"
        >
          ✕
        </button>
      </div>

      <details className="border-b border-line bg-card px-4 py-2">
        <summary className="cursor-pointer text-sm font-medium text-ink/75">
          Zutaten ({dish.recipe.zutaten.length})
        </summary>
        <ul className="mt-2 space-y-1 pb-2 text-sm text-ink/75">
          {dish.recipe.zutaten.map((ing, i) => (
            <li key={i}>
              {ing.menge && <span className="font-medium">{ing.menge} {ing.einheit} </span>}
              {ing.name}
            </li>
          ))}
        </ul>
      </details>

      <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto p-6 text-center">
        <p className="mb-4 font-display text-sm font-semibold uppercase tracking-wide text-olive">
          Schritt {step + 1}/{steps.length}
        </p>
        <p className="max-w-md text-xl leading-relaxed text-ink">{steps[step]}</p>
      </div>

      <div
        className="flex items-center gap-3 border-t border-line bg-card p-4"
        style={{ paddingBottom: 'max(1rem, env(safe-area-inset-bottom))' }}
      >
        <button
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
          className="min-h-14 flex-1 basis-1/2 rounded-xl bg-olive-soft py-4 text-lg font-medium text-ink/75 disabled:opacity-30"
        >
          ← Zurück
        </button>
        <button
          onClick={() => (step < steps.length - 1 ? setStep((s) => s + 1) : onClose())}
          className="min-h-14 flex-1 basis-1/2 rounded-xl bg-olive py-4 text-lg font-medium text-olive-on hover:bg-olive-hover"
        >
          {step < steps.length - 1 ? 'Weiter →' : 'Fertig'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Plan page
// ---------------------------------------------------------------------------

export default function Plan() {
  const { planId } = useParams<{ planId: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [plan, setPlan] = useState<Plan | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'recipes' | 'shopping'>('recipes')

  const dishParam = searchParams.get('dish')
  const initialOpenDishId = dishParam ? Number(dishParam) : null

  const loadPlan = useCallback(async () => {
    try {
      const data = await apiFetch<Plan>(`/plans/${planId}`)
      setPlan(data)
    } catch {
      //
    } finally {
      setLoading(false)
    }
  }, [planId])

  useEffect(() => {
    loadPlan()
  }, [loadPlan])

  function updateShoppingItem(id: number, changes: Partial<ShoppingItem>) {
    setPlan((prev) =>
      prev
        ? {
            ...prev,
            shopping_items: prev.shopping_items?.map((i) =>
              i.id === id ? { ...i, ...changes } : i
            ),
          }
        : prev
    )
  }

  function addShoppingItem(item: ShoppingItem) {
    setPlan((prev) =>
      prev ? { ...prev, shopping_items: [...(prev.shopping_items || []), item] } : prev
    )
  }

  function removeShoppingItem(id: number) {
    setPlan((prev) =>
      prev
        ? { ...prev, shopping_items: (prev.shopping_items || []).filter((i) => i.id !== id) }
        : prev
    )
  }

  const syncShoppingItems = useCallback((items: ShoppingItem[]) => {
    setPlan((prev) => (prev ? { ...prev, shopping_items: items } : prev))
  }, [])

  if (loading) {
    return (
      <main className="mx-auto max-w-xl px-4 py-5 sm:p-6">
        <div className="flex items-center justify-center py-16 text-muted">Lädt…</div>
      </main>
    )
  }

  if (!plan) {
    return (
      <main className="mx-auto max-w-xl px-4 py-5 sm:p-6">
        <p className="text-red-600 dark:text-red-400">Plan nicht gefunden.</p>
        <button onClick={() => navigate('/')} className="mt-2 text-sm underline">Home</button>
      </main>
    )
  }

  const confirmed = (plan.dishes || []).filter((d) => d.dish_status === 'confirmed')

  return (
    <main className="mx-auto max-w-xl px-4 py-5 sm:p-6">
      <div className="mb-6 flex items-center justify-between gap-2">
        <button onClick={() => navigate('/')} className="shrink-0 text-sm text-muted underline hover:text-ink">
          Zurück
        </button>
        <span className="shrink-0 text-xs text-muted">KW ab {plan.week_start_date}</span>
      </div>

      {plan.status === 'pending' && (
        <PendingView onRefresh={loadPlan} />
      )}

      {plan.status === 'confirming' && (
        <PendingView onRefresh={loadPlan} message="Plan wird aktualisiert…" />
      )}

      {plan.status === 'error' && (
        <div className="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/40 p-6 text-center">
          <p className="font-medium text-red-700 dark:text-red-300">Vorschläge konnten nicht generiert werden</p>
          <p className="mt-1 text-sm text-red-600 dark:text-red-400">
            Prüfe ob der OpenRouter-API-Key in <code className="font-mono">backend/.env</code> gesetzt ist
            und die Modelle verfügbar sind.
          </p>
          <button
            onClick={() => navigate('/plan/new')}
            className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
          >
            Neu versuchen
          </button>
        </div>
      )}

      {plan.status === 'suggestions_ready' && (
        <SuggestionsView
          plan={plan}
          onConfirmed={(updated) => setPlan(updated)}
          onReload={loadPlan}
        />
      )}

      {plan.status === 'confirmed' && (
        <div>
          {plan.savings && plan.savings.offers_used > 0 && (
            <div className="mb-4 rounded-xl border border-honey/40 bg-honey-soft px-4 py-3 text-sm font-medium text-ink">
              🏷️ {formatSavingsBanner(plan.savings)}
            </div>
          )}

          <div className="mb-4 flex gap-2">
            <button
              onClick={() => setTab('recipes')}
              className={`flex-1 rounded-full px-4 py-2.5 text-sm font-medium transition-colors ${tab === 'recipes' ? 'bg-olive text-olive-on' : 'bg-olive-soft text-ink/75 hover:bg-line'}`}
            >
              Rezepte ({confirmed.length})
            </button>
            <button
              onClick={() => setTab('shopping')}
              className={`flex-1 rounded-full px-4 py-2.5 text-sm font-medium transition-colors ${tab === 'shopping' ? 'bg-olive text-olive-on' : 'bg-olive-soft text-ink/75 hover:bg-line'}`}
            >
              Einkaufsliste ({(plan.shopping_items || []).filter((i) => !i.is_checked && !i.is_already_have).length})
            </button>
          </div>

          {tab === 'recipes' && (
            <RecipesView plan={plan} onReload={loadPlan} initialOpenDishId={initialOpenDishId} />
          )}
          {tab === 'shopping' && (
            <ShoppingView
              plan={plan}
              onItemUpdate={updateShoppingItem}
              onItemAdded={addShoppingItem}
              onItemRemoved={removeShoppingItem}
              onSync={syncShoppingItems}
            />
          )}
        </div>
      )}
    </main>
  )
}
