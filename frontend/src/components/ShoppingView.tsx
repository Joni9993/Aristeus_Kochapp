// Full shopping list for one plan — checkboxes, store grouping, "Habe ich",
// share, add-item form, and a 10s poll so changes on another device show up
// here too. Extracted from Plan.tsx (task 6) so it can be reused by both the
// Plan page (embedded, one of two tabs) and the standalone /shopping page.
import { useEffect, useRef, useState, type RefObject } from 'react'
import { apiFetch } from '../api/client'
import type { Plan, ShoppingItem } from '../types'

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

export default function ShoppingView({
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

  // Floating "+" button (thumb-reachable) that mirrors the always-present
  // add-item form at the bottom of the list. An IntersectionObserver watches
  // that form's wrapping card: once it scrolls into view the FAB fades/
  // shrinks away (visually "melts into" the form instead of just vanishing),
  // and reappears once the form scrolls back out of view. Tapping the FAB
  // scrolls the form into view and focuses its input.
  const addFormRef = useRef<HTMLDivElement>(null)
  const addInputRef = useRef<HTMLInputElement>(null)
  const [addFormVisible, setAddFormVisible] = useState(false)

  useEffect(() => {
    const el = addFormRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => setAddFormVisible(entry.isIntersecting),
      { threshold: 0.15 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  function focusAddForm() {
    addFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    // Wait for the scroll to (roughly) land before focusing, so the on-screen
    // keyboard doesn't fight the smooth-scroll animation on mobile.
    window.setTimeout(() => addInputRef.current?.focus(), 400)
  }

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
      // Whole row toggles is_checked (bigger tap target than the checkbox
      // alone); the two action buttons stop propagation so they act on
      // their own tap instead of double-toggling.
      <div
        onClick={() => toggle(item, 'is_checked')}
        className={`flex cursor-pointer items-center gap-3 py-2.5 border-b border-line last:border-0 active:bg-surface ${dimmed ? 'opacity-50' : ''}`}
      >
        <input
          type="checkbox"
          checked={item.is_checked}
          onChange={() => toggle(item, 'is_checked')}
          onClick={(e) => e.stopPropagation()}
          className="h-5 w-5 shrink-0 accent-olive"
        />
        <div className="min-w-0 flex-1">
          <span className={`text-sm ${item.is_checked ? 'line-through text-muted' : 'text-ink'}`}>
            {showQty && <span className="font-medium">{item.quantity} {item.unit} </span>}
            {item.ingredient}
          </span>
          {angebot && (
            <span className="ml-1.5 inline-block rounded-full bg-honey-soft px-1.5 py-0.5 text-xs font-medium text-ink align-middle">
              Angebot{item.price_text ? ` · ${item.price_text}` : ''}
            </span>
          )}
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); toggle(item, 'is_already_have') }}
          title="Schon vorhanden"
          className={`shrink-0 rounded-full px-3 py-2 text-xs ${item.is_already_have ? 'bg-olive-soft text-olive' : 'text-muted hover:text-ink active:text-ink'}`}
        >
          Habe ich
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); removeItem(item) }}
          title="Entfernen"
          aria-label="Entfernen"
          className="shrink-0 p-2 text-muted/60 hover:text-red-500 active:text-red-500"
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
        <h2 className="font-display text-lg font-semibold text-ink">Einkaufsliste</h2>
        <button onClick={shareList} className="shrink-0 rounded-lg border border-line px-3 py-2 text-xs text-ink hover:bg-card">
          Teilen
        </button>
      </div>

      {allItems.length === 0 && <p className="text-sm text-muted">Keine Zutaten.</p>}

      {storeKeys.map((storeKey) => {
        const storeItems = groups.get(storeKey)!
        const label = STORE_LABELS[storeKey] || (storeKey ? storeKey : null)
        return (
          <div key={storeKey || '__none__'} className="mb-4">
            {label && (
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
            )}
            <div className="rounded-xl border border-line bg-card px-3">
              {storeItems.map((item) => <ItemRow key={item.id} item={item} />)}
            </div>
          </div>
        )
      })}

      {pantryItems.length > 0 && (
        <div className="mb-4">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
            Gewürze &amp; Pantry — wahrscheinlich zuhause
          </p>
          <div className="rounded-xl border border-line bg-surface px-3">
            {pantryItems.map((item) => <ItemRow key={item.id} item={item} dimmed />)}
          </div>
        </div>
      )}

      {done.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-muted">
            {done.length} erledigt / vorhanden
          </summary>
          <div className="mt-2 rounded-xl border border-line bg-card px-3 opacity-60">
            {done.map((item) => <ItemRow key={item.id} item={item} />)}
          </div>
        </details>
      )}

      <div ref={addFormRef} className="mt-4 rounded-xl border border-line bg-card p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
          Eigenes hinzufügen
        </p>
        <AddItemForm onAdd={addItem} inputRef={addInputRef} />
      </div>

      {/* Thumb-reachable shortcut to the add-item form above. Fades/shrinks
          out once that form is itself on screen, so it visually "hands off"
          to it instead of overlapping it. z-20 keeps it below the z-30
          BottomNav so it never covers (or gets covered oddly relative to)
          the tab bar. */}
      <button
        onClick={focusAddForm}
        aria-label="Eigenes hinzufügen"
        aria-hidden={addFormVisible}
        tabIndex={addFormVisible ? -1 : 0}
        className={`fixed right-4 z-20 flex min-h-14 min-w-14 items-center justify-center rounded-full bg-olive text-olive-on shadow-lg transition-all duration-300 ease-out hover:bg-olive-hover active:bg-olive-hover ${
          addFormVisible ? 'pointer-events-none scale-50 opacity-0' : 'scale-100 opacity-100'
        }`}
        style={{ bottom: 'calc(6rem + env(safe-area-inset-bottom))' }}
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="h-7 w-7">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
        </svg>
      </button>
    </div>
  )
}

function AddItemForm({
  onAdd,
  inputRef,
}: {
  onAdd: (ingredient: string) => Promise<void>
  inputRef?: RefObject<HTMLInputElement>
}) {
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
    // min-w-0 on the input is required here: as a flex-1 child its default
    // min-width is "auto" (content-based), which was letting a long typed
    // value push the button off the right edge on narrow screens.
    <div className="flex gap-2">
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="Eigenes hinzufügen…"
        className="min-h-11 min-w-0 flex-1 rounded-lg border border-line px-3 py-2 text-sm focus:border-olive focus:outline-none"
      />
      <button
        onClick={submit}
        disabled={adding || !value.trim()}
        aria-label="Hinzufügen"
        className="min-h-11 shrink-0 rounded-lg bg-olive px-4 text-sm font-medium text-olive-on hover:bg-olive-hover disabled:opacity-50"
      >
        {adding ? '…' : 'Hinzufügen'}
      </button>
    </div>
  )
}
