import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Dish = {
  id: number
  name: string
  description: string | null
  cuisine: string | null
  cook_time_min: number | null
  cook_day: string | null
  dish_status: 'suggestion' | 'confirmed' | 'rejected'
  is_favorite: boolean
  feedback_thumbs: number | null
  feedback_portion_note: string | null
  feedback_free_text: string | null
  recipe: Recipe | null
}

type RecipeIngredient = {
  name: string
  menge: number | null
  einheit: string | null
  ist_angebot: boolean
}

type Recipe = {
  zutaten: RecipeIngredient[]
  schritte: string[]
  geschaetzte_zeit_min: number
  tipps: string[]
}

type ShoppingItem = {
  id: number
  ingredient: string
  quantity: string | null
  unit: string | null
  store: string | null
  live_from_date: string | null
  is_checked: boolean
  is_already_have: boolean
}

type Plan = {
  id: number
  week_start_date: string
  status: string
  created_at: string
  dishes?: Dish[]
  shopping_items?: ShoppingItem[]
}

const DAYS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

// ---------------------------------------------------------------------------
// Pending view
// ---------------------------------------------------------------------------

function PendingView({ onRefresh }: { onRefresh: () => void }) {
  useEffect(() => {
    const t = setInterval(onRefresh, 3000)
    return () => clearInterval(t)
  }, [onRefresh])

  return (
    <div className="flex flex-col items-center gap-4 py-12 text-stone-500">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-emerald-400 border-t-transparent" />
      <p className="text-sm">Gerichte werden vorgeschlagen…</p>
      <p className="text-xs text-stone-400">Das dauert ca. 10–30 Sekunden</p>
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
  const cuisineColor: Record<string, string> = {
    vegetarisch: 'bg-emerald-100 text-emerald-700',
    vegan: 'bg-green-100 text-green-700',
    Fisch: 'bg-blue-100 text-blue-700',
    Fleisch: 'bg-amber-100 text-amber-700',
    gemischt: 'bg-stone-100 text-stone-600',
  }
  const color = cuisineColor[dish.cuisine || 'gemischt'] || 'bg-stone-100 text-stone-600'

  return (
    <div
      className={`rounded-xl border p-4 transition-all ${
        sel.checked ? 'border-emerald-400 bg-emerald-50' : 'border-stone-200 bg-white'
      }`}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={sel.checked}
          onChange={(e) => onChange({ ...sel, checked: e.target.checked })}
          className="mt-1 h-4 w-4 accent-emerald-600"
        />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="font-semibold text-stone-800 leading-tight">{dish.name}</span>
            {dish.cuisine && (
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
                {dish.cuisine}
              </span>
            )}
            {dish.cook_time_min && (
              <span className="text-xs text-stone-400">{dish.cook_time_min} Min.</span>
            )}
          </div>
          {dish.description && (
            <p className="text-sm text-stone-500 leading-snug">{dish.description}</p>
          )}
        </div>
      </div>

      {sel.checked && (
        <div className="mt-3 ml-7">
          <label className="mb-1 block text-xs text-stone-500">Wochentag</label>
          <select
            value={sel.cook_day}
            onChange={(e) => onChange({ ...sel, cook_day: e.target.value })}
            className="rounded-lg border border-stone-300 px-2 py-1 text-sm"
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

  const selected = dishes.filter((d) => selections[d.id]?.checked)

  async function handleMoreSuggestions() {
    setLoadingMore(true)
    setError('')
    try {
      await apiFetch(`/plans/${plan.id}/more-suggestions`, { method: 'POST' })
      onReload()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler')
    } finally {
      setLoadingMore(false)
    }
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
        body: JSON.stringify({ selections: sels }),
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
        <h2 className="font-semibold text-stone-800">Gerichtsvorschläge</h2>
        <span className="text-xs text-stone-400">{selected.length} ausgewählt</span>
      </div>

      {error && <p className="mb-3 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

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
          className="mb-4 w-full rounded-lg border border-stone-300 py-2 text-sm text-stone-600 hover:bg-stone-50 disabled:opacity-50"
        >
          {loadingMore ? 'Lädt…' : '+ 5 weitere Vorschläge'}
        </button>
      )}

      <button
        onClick={handleConfirm}
        disabled={confirming || selected.length === 0}
        className="w-full rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        {confirming ? 'Rezepte werden generiert…' : `${selected.length} Gerichte übernehmen`}
      </button>
      {confirming && (
        <p className="mt-2 text-center text-xs text-stone-400">Dauert ca. 30–60 Sekunden…</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Recipes view
// ---------------------------------------------------------------------------

function RecipesView({ plan }: { plan: Plan }) {
  const [open, setOpen] = useState<number | null>(null)
  const confirmed = (plan.dishes || []).filter((d) => d.dish_status === 'confirmed')

  return (
    <div>
      <h2 className="mb-4 font-semibold text-stone-800">Rezepte</h2>
      <div className="space-y-2">
        {confirmed.map((d) => (
          <div key={d.id} className="rounded-xl border border-stone-200 overflow-hidden">
            <button
              className="flex w-full items-center justify-between p-4 text-left hover:bg-stone-50"
              onClick={() => setOpen(open === d.id ? null : d.id)}
            >
              <div>
                <span className="font-medium">{d.name}</span>
                {d.cook_day && (
                  <span className="ml-2 text-xs text-stone-400">{d.cook_day}</span>
                )}
              </div>
              <span className="text-stone-400">{open === d.id ? '▲' : '▼'}</span>
            </button>

            {open === d.id && d.recipe && (
              <div className="border-t border-stone-100 p-4 text-sm">
                <h3 className="mb-2 font-semibold text-stone-700">Zutaten</h3>
                <ul className="mb-4 space-y-1">
                  {d.recipe.zutaten.map((ing, i) => (
                    <li key={i} className="flex gap-2 text-stone-600">
                      {ing.menge && <span className="font-medium">{ing.menge} {ing.einheit}</span>}
                      <span>{ing.name}</span>
                      {ing.ist_angebot && (
                        <span className="rounded bg-emerald-100 px-1 text-xs text-emerald-700">Angebot</span>
                      )}
                    </li>
                  ))}
                </ul>

                <h3 className="mb-2 font-semibold text-stone-700">Zubereitung</h3>
                <ol className="mb-4 space-y-1 list-decimal list-inside">
                  {d.recipe.schritte.map((step, i) => (
                    <li key={i} className="text-stone-600 leading-relaxed">{step}</li>
                  ))}
                </ol>

                {d.recipe.tipps.length > 0 && (
                  <>
                    <h3 className="mb-2 font-semibold text-stone-700">Tipps</h3>
                    <ul className="space-y-1">
                      {d.recipe.tipps.map((tip, i) => (
                        <li key={i} className="text-stone-500">💡 {tip}</li>
                      ))}
                    </ul>
                  </>
                )}

                <FeedbackRow planId={plan.id} dish={d} />
              </div>
            )}
            {open === d.id && !d.recipe && (
              <div className="border-t border-stone-100 p-4 text-sm text-stone-400">
                Kein Rezept verfügbar.
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function FeedbackRow({ planId, dish }: { planId: number; dish: Dish }) {
  const [thumbs, setThumbs] = useState<number | null>(dish.feedback_thumbs)
  const [portion, setPortion] = useState<string | null>(dish.feedback_portion_note)
  const [fav, setFav] = useState(dish.is_favorite)
  const [freeText, setFreeText] = useState(dish.feedback_free_text ?? '')
  const [saving, setSaving] = useState(false)
  const [textSaved, setTextSaved] = useState(false)

  async function sendPatch(patch: Record<string, unknown>) {
    try {
      await apiFetch(`/plans/${planId}/dishes/${dish.id}/feedback`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      })
    } catch {
      //
    }
  }

  async function handleThumbs(t: number) {
    setThumbs(t)
    await sendPatch({ thumbs: t })
  }

  async function handlePortion(opt: string) {
    const next = portion === opt ? '' : opt
    setPortion(next || null)
    await sendPatch({ portion_note: next })
  }

  async function handleFav() {
    const next = !fav
    setFav(next)
    await sendPatch({ is_favorite: next })
  }

  async function saveText() {
    setSaving(true)
    setTextSaved(false)
    await sendPatch({ free_text: freeText })
    setSaving(false)
    setTextSaved(true)
    setTimeout(() => setTextSaved(false), 2000)
  }

  return (
    <div className="mt-4 space-y-3 border-t border-stone-100 pt-3">
      <div className="flex items-center gap-3">
        <span className="text-xs text-stone-400">Wie war's?</span>
        <button
          onClick={() => handleThumbs(1)}
          className={`rounded-full px-3 py-1 text-sm ${thumbs === 1 ? 'bg-emerald-500 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'}`}
        >
          👍
        </button>
        <button
          onClick={() => handleThumbs(-1)}
          className={`rounded-full px-3 py-1 text-sm ${thumbs === -1 ? 'bg-red-400 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'}`}
        >
          👎
        </button>
        <button
          onClick={handleFav}
          className={`ml-auto text-lg leading-none ${fav ? 'text-amber-400' : 'text-stone-300 hover:text-stone-400'}`}
          title={fav ? 'Aus Favoriten entfernen' : 'Als Favorit merken'}
        >
          {fav ? '★' : '☆'}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-stone-400">Portion:</span>
        {(['zu wenig', 'genau richtig', 'zu viel'] as const).map((opt) => (
          <button
            key={opt}
            onClick={() => handlePortion(opt)}
            className={`rounded-full px-2 py-0.5 text-xs ${portion === opt ? 'bg-emerald-500 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'}`}
          >
            {opt}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <textarea
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          placeholder="Notiz (optional)…"
          rows={2}
          className="flex-1 resize-none rounded-lg border border-stone-200 p-2 text-sm focus:border-emerald-400 focus:outline-none"
        />
        <button
          onClick={saveText}
          disabled={saving}
          className="self-end rounded-lg bg-stone-100 px-3 py-1.5 text-xs text-stone-600 hover:bg-stone-200 disabled:opacity-50"
        >
          {saving ? '…' : textSaved ? '✓' : 'Speichern'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shopping view
// ---------------------------------------------------------------------------

function ShoppingView({ plan, onItemUpdate }: { plan: Plan; onItemUpdate: (id: number, changes: Partial<ShoppingItem>) => void }) {
  const items = plan.shopping_items || []
  const unchecked = items.filter((i) => !i.is_checked && !i.is_already_have)
  const checked = items.filter((i) => i.is_checked || i.is_already_have)

  async function toggle(item: ShoppingItem, field: 'is_checked' | 'is_already_have') {
    const newVal = !item[field]
    onItemUpdate(item.id, { [field]: newVal })
    try {
      await apiFetch(`/plans/${plan.id}/shopping/${item.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ [field]: newVal }),
      })
    } catch {
      onItemUpdate(item.id, { [field]: item[field] }) // revert
    }
  }

  function ItemRow({ item }: { item: ShoppingItem }) {
    return (
      <div className="flex items-center gap-3 py-2">
        <input
          type="checkbox"
          checked={item.is_checked}
          onChange={() => toggle(item, 'is_checked')}
          className="h-4 w-4 accent-emerald-600"
        />
        <div className="flex-1 min-w-0">
          <span className={`text-sm ${item.is_checked ? 'line-through text-stone-400' : 'text-stone-700'}`}>
            {item.quantity && <span className="font-medium">{item.quantity} {item.unit} </span>}
            {item.ingredient}
          </span>
          {item.store && (
            <span className="ml-2 text-xs text-stone-400">{item.store}</span>
          )}
        </div>
        <button
          onClick={() => toggle(item, 'is_already_have')}
          title="Schon vorhanden"
          className={`rounded-full px-2 py-0.5 text-xs ${item.is_already_have ? 'bg-blue-100 text-blue-700' : 'text-stone-300 hover:text-stone-500'}`}
        >
          Habe ich
        </button>
      </div>
    )
  }

  async function shareList() {
    const text = unchecked
      .map((i) => `☐ ${i.quantity ? i.quantity + ' ' + (i.unit || '') + ' ' : ''}${i.ingredient}`)
      .join('\n')
    if (navigator.share) {
      await navigator.share({ title: 'Einkaufsliste', text })
    } else {
      await navigator.clipboard.writeText(text)
      alert('Einkaufsliste in die Zwischenablage kopiert.')
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-semibold text-stone-800">Einkaufsliste</h2>
        <button
          onClick={shareList}
          className="rounded-lg border border-stone-300 px-3 py-1 text-xs hover:bg-stone-50"
        >
          Teilen
        </button>
      </div>

      {items.length === 0 && (
        <p className="text-sm text-stone-400">Keine Zutaten.</p>
      )}

      <div className="divide-y divide-stone-100">
        {unchecked.map((item) => <ItemRow key={item.id} item={item} />)}
      </div>

      {checked.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-stone-400">
            {checked.length} erledigt / vorhanden
          </summary>
          <div className="mt-1 divide-y divide-stone-100 opacity-60">
            {checked.map((item) => <ItemRow key={item.id} item={item} />)}
          </div>
        </details>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Plan page
// ---------------------------------------------------------------------------

export default function Plan() {
  const { planId } = useParams<{ planId: string }>()
  const navigate = useNavigate()
  const [plan, setPlan] = useState<Plan | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'recipes' | 'shopping'>('recipes')

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

  if (loading) {
    return (
      <main className="mx-auto max-w-xl p-6">
        <div className="flex items-center justify-center py-16 text-stone-400">Lädt…</div>
      </main>
    )
  }

  if (!plan) {
    return (
      <main className="mx-auto max-w-xl p-6">
        <p className="text-red-600">Plan nicht gefunden.</p>
        <button onClick={() => navigate('/')} className="mt-2 text-sm underline">Home</button>
      </main>
    )
  }

  const confirmed = (plan.dishes || []).filter((d) => d.dish_status === 'confirmed')

  return (
    <main className="mx-auto max-w-xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <button onClick={() => navigate('/')} className="text-sm text-stone-500 underline hover:text-stone-700">
          Zurück
        </button>
        <span className="text-xs text-stone-400">KW ab {plan.week_start_date}</span>
      </div>

      {plan.status === 'pending' && (
        <PendingView onRefresh={loadPlan} />
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
          <div className="mb-4 flex gap-2">
            <button
              onClick={() => setTab('recipes')}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'recipes' ? 'bg-emerald-600 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'}`}
            >
              Rezepte ({confirmed.length})
            </button>
            <button
              onClick={() => setTab('shopping')}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'shopping' ? 'bg-emerald-600 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'}`}
            >
              Einkaufsliste ({(plan.shopping_items || []).filter((i) => !i.is_checked && !i.is_already_have).length})
            </button>
          </div>

          {tab === 'recipes' && <RecipesView plan={plan} />}
          {tab === 'shopping' && (
            <ShoppingView plan={plan} onItemUpdate={updateShoppingItem} />
          )}
        </div>
      )}
    </main>
  )
}
