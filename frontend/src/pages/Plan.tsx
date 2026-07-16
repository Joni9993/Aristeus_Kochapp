import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import DishImage from '../components/DishImage'
import FeedbackRow from '../components/FeedbackRow'
import RecipeDetails from '../components/RecipeDetails'
import { cuisineBadgeClass, DAYS, germanWeekdayName } from '../types'
import type { Dish, Plan, ShoppingItem } from '../types'

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
    <div className="flex flex-col items-center gap-4 py-12 text-stone-500">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-emerald-400 border-t-transparent" />
      <p className="text-sm">{message}</p>
      <p className="text-xs text-stone-400">
        {elapsed < 90 ? 'Das dauert ca. 10–30 Sekunden' : `${elapsed}s — dauert ungewöhnlich lang`}
      </p>
      {elapsed >= 120 && (
        <button
          onClick={() => navigate('/plan/new')}
          className="mt-2 rounded-lg border border-stone-300 px-4 py-2 text-xs text-stone-600 hover:bg-stone-50"
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
        sel.checked ? 'border-emerald-400 bg-emerald-50' : 'border-stone-200 bg-white'
      }`}
    >
      <DishImage imageUrl={dish.image_url} name={dish.name} cuisine={dish.cuisine} className="h-36" />
      <div className="flex items-start gap-3 p-4">
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
        <div className="px-4 pb-4">
          <label className="mb-1 block text-xs text-stone-500">Wochentag</label>
          <select
            value={sel.cook_day}
            onChange={(e) => onChange({ ...sel, cook_day: e.target.value })}
            className="w-full rounded-lg border border-stone-300 px-2 py-2"
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

function RecipesView({ plan, onReload }: { plan: Plan; onReload: () => void }) {
  const [open, setOpen] = useState<number | null>(null)
  const [cookModeDish, setCookModeDish] = useState<Dish | null>(null)
  const itemRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const confirmed = (plan.dishes || []).filter((d) => d.dish_status === 'confirmed')
  const flexible = confirmed.filter((d) => !d.cook_day)
  const todayName = germanWeekdayName(new Date())

  function openDish(id: number) {
    setOpen(id)
    requestAnimationFrame(() => {
      itemRefs.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  async function handleSwap(dish: Dish) {
    if (!confirm(`${dish.name} durch ein neues Gericht ersetzen? Die Einkaufsliste wird angepasst.`)) return
    try {
      await apiFetch(`/plans/${plan.id}/dishes/${dish.id}/swap`, { method: 'POST' })
    } catch {
      // ignore — reload shows current state either way
    }
    onReload()
  }

  return (
    <div>
      <h2 className="mb-4 font-semibold text-stone-800">Rezepte</h2>

      {/* Wochenkalender */}
      <div className="mb-2 grid grid-cols-7 gap-1">
        {DAYS.map((day) => {
          const dish = confirmed.find((d) => d.cook_day === day)
          const isToday = day === todayName
          return (
            <button
              key={day}
              onClick={() => dish && openDish(dish.id)}
              disabled={!dish}
              className={`flex flex-col items-center gap-1 rounded-lg p-1.5 text-center transition-colors ${
                isToday ? 'bg-emerald-100' : 'bg-stone-50'
              } ${dish ? 'cursor-pointer hover:bg-emerald-50' : 'cursor-default opacity-40'}`}
            >
              <span className={`text-xs font-semibold ${isToday ? 'text-emerald-700' : 'text-stone-500'}`}>
                {day.slice(0, 2)}
              </span>
              <span className="line-clamp-2 text-[10px] leading-tight text-stone-600">
                {dish ? dish.name : '–'}
              </span>
            </button>
          )
        })}
      </div>

      {flexible.length > 0 && (
        <div className="mb-4 rounded-lg bg-stone-50 px-3 py-2 text-xs text-stone-500">
          <span className="font-semibold">Flexibel: </span>
          {flexible.map((d, i) => (
            <span key={d.id}>
              <button onClick={() => openDish(d.id)} className="underline hover:text-emerald-700">
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
            className="rounded-xl border border-stone-200 overflow-hidden"
          >
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
              <div className="border-t border-stone-100 text-sm">
                <DishImage imageUrl={d.image_url} name={d.name} cuisine={d.cuisine} className="h-48" />
                <div className="p-4">
                <RecipeDetails recipe={d.recipe} />

                <div className="mt-4 flex flex-wrap gap-2 border-t border-stone-100 pt-3">
                  <button
                    onClick={() => setCookModeDish(d)}
                    className="rounded-lg border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
                  >
                    👨‍🍳 Kochmodus
                  </button>
                  <button
                    onClick={() => handleSwap(d)}
                    className="rounded-lg border border-stone-300 px-3 py-1.5 text-xs text-stone-600 hover:bg-stone-50"
                  >
                    🔄 Gericht tauschen
                  </button>
                </div>

                <FeedbackRow planId={plan.id} dish={d} />
                </div>
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
    <div className="fixed inset-0 z-50 flex flex-col bg-stone-50">
      <div className="flex items-center justify-between border-b border-stone-200 bg-white px-4 py-3">
        <span className="font-semibold text-stone-800">{dish.name}</span>
        <button
          onClick={onClose}
          className="text-xl leading-none text-stone-400 hover:text-stone-600"
          aria-label="Schließen"
        >
          ✕
        </button>
      </div>

      <details className="border-b border-stone-200 bg-white px-4 py-2">
        <summary className="cursor-pointer text-sm font-medium text-stone-600">
          Zutaten ({dish.recipe.zutaten.length})
        </summary>
        <ul className="mt-2 space-y-1 pb-2 text-sm text-stone-600">
          {dish.recipe.zutaten.map((ing, i) => (
            <li key={i}>
              {ing.menge && <span className="font-medium">{ing.menge} {ing.einheit} </span>}
              {ing.name}
            </li>
          ))}
        </ul>
      </details>

      <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto p-6 text-center">
        <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-stone-400">
          Schritt {step + 1}/{steps.length}
        </p>
        <p className="max-w-md text-xl leading-relaxed text-stone-800">{steps[step]}</p>
      </div>

      <div className="flex items-center gap-3 border-t border-stone-200 bg-white p-4">
        <button
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
          className="flex-1 rounded-xl bg-stone-100 py-4 text-lg font-medium text-stone-600 disabled:opacity-30"
        >
          ← Zurück
        </button>
        <button
          onClick={() => (step < steps.length - 1 ? setStep((s) => s + 1) : onClose())}
          className="flex-1 rounded-xl bg-emerald-600 py-4 text-lg font-medium text-white hover:bg-emerald-700"
        >
          {step < steps.length - 1 ? 'Weiter →' : 'Fertig'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shopping view
// ---------------------------------------------------------------------------

const STORE_LABELS: Record<string, string> = {
  rewe: 'Rewe', lidl: 'Lidl', aldi: 'Aldi', edeka: 'Edeka',
  penny: 'Penny', netto: 'Netto', kaufland: 'Kaufland',
}

const PANTRY_RE = /^(salz|pfeffer|paprikapulver|curry|kurkuma|zimt|zucker|mehl|essig|backpulver|natron|hefe)\b/i

function isPantry(item: ShoppingItem): boolean {
  const n = item.ingredient.toLowerCase()
  return n.endsWith('öl') || PANTRY_RE.test(n)
}

function getFoodCategory(ingredient: string): number {
  const n = ingredient.toLowerCase()
  if (/paprika|brokkoli|tomate|zwiebel|knoblauch|karotte|salat|gurke|zucchini|spinat|kohl|pilz|champignon|petersilie|dill|zitrone|kräuter|avocado|mais/.test(n)) return 1
  if (/hähnchen|hühnchen|pute|rind|schwein|wurst|aufschnitt|hack|schinken|gyros|geschnetzeltes|fleisch|speck/.test(n)) return 2
  if (/lachs|thunfisch|garnelen|fisch|meeresfrüchte|forelle/.test(n)) return 3
  if (/milch|käse|joghurt|skyr|schmand|frischkäse|kräuterbutter|cheddar|mozzarella|ei |eier|quark|sahne|butter/.test(n)) return 4
  if (/brot|brötchen|toast|semmel|sesambrötchen/.test(n)) return 5
  if (/nudeln|pasta|spaghetti|penne|reis|getreide|couscous|bulgur/.test(n)) return 6
  if (/dose|bohnen|linsen|kichererbsen/.test(n)) return 7
  return 8
}

function ShoppingView({
  plan,
  onItemUpdate,
  onItemAdded,
  onItemRemoved,
  onSync,
}: {
  plan: Plan
  onItemUpdate: (id: number, changes: Partial<ShoppingItem>) => void
  onItemAdded: (item: ShoppingItem) => void
  onItemRemoved: (id: number) => void
  onSync: (items: ShoppingItem[]) => void
}) {
  const allItems = plan.shopping_items || []

  // Build angebot ingredient set from recipe data (fallback for plans without store set)
  const angebotNames = new Set<string>()
  for (const dish of plan.dishes || []) {
    if (!dish.recipe) continue
    for (const ing of dish.recipe.zutaten) {
      if (ing.ist_angebot) angebotNames.add(ing.name.toLowerCase())
    }
  }
  function isAngebot(item: ShoppingItem) {
    return item.is_angebot || angebotNames.has(item.ingredient.toLowerCase())
  }

  // Periodically pull shopping_items from the server so changes made on
  // another device show up here too — only while this tab is visible and
  // mounted. Replaces shopping_items wholesale (simplest robust approach);
  // the add-item input keeps its own local state so in-progress typing
  // survives a sync.
  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState !== 'visible') return
      apiFetch<Plan>(`/plans/${plan.id}`)
        .then((p) => onSync(p.shopping_items || []))
        .catch(() => {})
    }, 10000)
    return () => clearInterval(interval)
  }, [plan.id, onSync])

  async function toggle(item: ShoppingItem, field: 'is_checked' | 'is_already_have') {
    const newVal = !item[field]
    onItemUpdate(item.id, { [field]: newVal })
    try {
      await apiFetch(`/plans/${plan.id}/shopping/${item.id}`, {
        method: 'PATCH',
        body: { [field]: newVal },
      })
    } catch {
      onItemUpdate(item.id, { [field]: item[field] })
    }
  }

  async function removeItem(item: ShoppingItem) {
    onItemRemoved(item.id)
    try {
      await apiFetch(`/plans/${plan.id}/shopping/${item.id}`, { method: 'DELETE' })
    } catch {
      onItemAdded(item)
    }
  }

  async function addItem(ingredient: string) {
    try {
      const item = await apiFetch<ShoppingItem>(`/plans/${plan.id}/shopping`, {
        method: 'POST',
        body: { ingredient },
      })
      onItemAdded(item)
    } catch {
      // silently ignore — user can retype
    }
  }

  function ItemRow({ item, dimmed = false }: { item: ShoppingItem; dimmed?: boolean }) {
    const angebot = isAngebot(item)
    const showQty = item.quantity && item.quantity !== '0'
    return (
      <div className={`flex items-center gap-3 py-2.5 border-b border-stone-100 last:border-0 ${dimmed ? 'opacity-50' : ''}`}>
        <input
          type="checkbox"
          checked={item.is_checked}
          onChange={() => toggle(item, 'is_checked')}
          className="h-4 w-4 shrink-0 accent-emerald-600"
        />
        <div className="flex-1 min-w-0">
          <span className={`text-sm ${item.is_checked ? 'line-through text-stone-400' : 'text-stone-700'}`}>
            {showQty && <span className="font-medium">{item.quantity} {item.unit} </span>}
            {item.ingredient}
          </span>
          {angebot && (
            <span className="ml-1.5 inline-block rounded-full bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-700 align-middle">
              Angebot{item.price_text ? ` · ${item.price_text}` : ''}
            </span>
          )}
        </div>
        <button
          onClick={() => toggle(item, 'is_already_have')}
          title="Schon vorhanden"
          className={`shrink-0 rounded-full px-3 py-1.5 text-xs ${item.is_already_have ? 'bg-sky-100 text-sky-700' : 'text-stone-400 hover:text-stone-600 active:text-stone-600'}`}
        >
          Habe ich
        </button>
        <button
          onClick={() => removeItem(item)}
          title="Entfernen"
          aria-label="Entfernen"
          className="shrink-0 text-stone-300 hover:text-red-500 active:text-red-500"
        >
          ✕
        </button>
      </div>
    )
  }

  const active = allItems.filter((i) => !i.is_checked && !i.is_already_have)
  const done = allItems.filter((i) => i.is_checked || i.is_already_have)

  const pantryItems = active.filter(isPantry)
  const shopItems = active.filter((i) => !isPantry(i))

  // Group by store, sort each group by food category
  const groups = new Map<string, ShoppingItem[]>()
  for (const item of shopItems) {
    const key = item.store || ''
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(item)
  }
  for (const items of groups.values()) {
    items.sort((a, b) => getFoodCategory(a.ingredient) - getFoodCategory(b.ingredient))
  }
  const storeKeys = [...groups.keys()].sort((a, b) => {
    if (!a && b) return 1
    if (a && !b) return -1
    return a.localeCompare(b)
  })

  async function shareList() {
    const lines: string[] = []
    for (const key of storeKeys) {
      const label = STORE_LABELS[key] || (key || 'Sonstiges')
      const its = groups.get(key)!
      if (its.length) {
        lines.push(`=== ${label} ===`)
        for (const i of its) {
          const q = i.quantity && i.quantity !== '0' ? `${i.quantity} ${i.unit || ''} ` : ''
          lines.push(`☐ ${q}${i.ingredient}`)
        }
        lines.push('')
      }
    }
    if (pantryItems.length) {
      lines.push('=== Gewürze & Pantry ===')
      for (const i of pantryItems) lines.push(`☐ ${i.ingredient}`)
    }
    const text = lines.join('\n').trim()
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
        <button onClick={shareList} className="rounded-lg border border-stone-300 px-3 py-1 text-xs hover:bg-stone-50">
          Teilen
        </button>
      </div>

      {allItems.length === 0 && <p className="text-sm text-stone-400">Keine Zutaten.</p>}

      {storeKeys.map((storeKey) => {
        const storeItems = groups.get(storeKey)!
        const label = STORE_LABELS[storeKey] || (storeKey ? storeKey : null)
        return (
          <div key={storeKey || '__none__'} className="mb-4">
            {label && (
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">{label}</p>
            )}
            <div className="rounded-xl border border-stone-200 bg-white px-3">
              {storeItems.map((item) => <ItemRow key={item.id} item={item} />)}
            </div>
          </div>
        )
      })}

      {pantryItems.length > 0 && (
        <div className="mb-4">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-400">
            Gewürze &amp; Pantry — wahrscheinlich zuhause
          </p>
          <div className="rounded-xl border border-stone-100 bg-stone-50 px-3">
            {pantryItems.map((item) => <ItemRow key={item.id} item={item} dimmed />)}
          </div>
        </div>
      )}

      {done.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-stone-400">
            {done.length} erledigt / vorhanden
          </summary>
          <div className="mt-2 rounded-xl border border-stone-200 bg-white px-3 opacity-60">
            {done.map((item) => <ItemRow key={item.id} item={item} />)}
          </div>
        </details>
      )}

      <div className="mt-4 rounded-xl border border-stone-200 bg-white p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-500">
          Eigenes hinzufügen
        </p>
        <AddItemForm onAdd={addItem} />
      </div>
    </div>
  )
}

function AddItemForm({ onAdd }: { onAdd: (ingredient: string) => Promise<void> }) {
  const [value, setValue] = useState('')
  const [adding, setAdding] = useState(false)

  async function submit() {
    const v = value.trim()
    if (!v) return
    setAdding(true)
    await onAdd(v)
    setValue('')
    setAdding(false)
  }

  return (
    <div className="flex gap-2">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="Eigenes hinzufügen…"
        className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
      />
      <button
        onClick={submit}
        disabled={adding || !value.trim()}
        className="shrink-0 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        {adding ? '…' : 'Hinzufügen'}
      </button>
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

      {plan.status === 'confirming' && (
        <PendingView onRefresh={loadPlan} message="Plan wird aktualisiert…" />
      )}

      {plan.status === 'error' && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
          <p className="font-medium text-red-700">Vorschläge konnten nicht generiert werden</p>
          <p className="mt-1 text-sm text-red-600">
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
            <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              🏷️ {plan.savings.offers_used} Angebote genutzt · zusammen{' '}
              {plan.savings.offer_total.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
            </div>
          )}

          <div className="mb-4 flex gap-2">
            <button
              onClick={() => setTab('recipes')}
              className={`flex-1 rounded-full px-4 py-2.5 text-sm font-medium transition-colors ${tab === 'recipes' ? 'bg-emerald-600 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'}`}
            >
              Rezepte ({confirmed.length})
            </button>
            <button
              onClick={() => setTab('shopping')}
              className={`flex-1 rounded-full px-4 py-2.5 text-sm font-medium transition-colors ${tab === 'shopping' ? 'bg-emerald-600 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'}`}
            >
              Einkaufsliste ({(plan.shopping_items || []).filter((i) => !i.is_checked && !i.is_already_have).length})
            </button>
          </div>

          {tab === 'recipes' && <RecipesView plan={plan} onReload={loadPlan} />}
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
