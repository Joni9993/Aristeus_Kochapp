import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import DishImage from '../components/DishImage'
import RecipeDetails from '../components/RecipeDetails'
import { cookbookEntryKey, cuisineBadgeClass, DAYS } from '../types'
import type { CookbookEntry } from '../types'

// ---------------------------------------------------------------------------
// Add-recipe dialog: URL import / manual entry
// ---------------------------------------------------------------------------

function UrlImportForm({ onAdded }: { onAdded: (entry: CookbookEntry) => void }) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    const v = url.trim()
    if (!v) return
    setLoading(true)
    setError('')
    try {
      const entry = await apiFetch<CookbookEntry>('/recipes/import', {
        method: 'POST',
        body: { url: v },
      })
      onAdded(entry)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler beim Import')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      <input
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://…"
        inputMode="url"
        className="w-full min-w-0 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
      />
      {error && <p className="rounded bg-red-50 p-2 text-xs text-red-700">{error}</p>}
      <button
        onClick={submit}
        disabled={loading || !url.trim()}
        className="min-h-11 w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        {loading ? 'Rezept wird gelesen…' : 'Importieren'}
      </button>
    </div>
  )
}

type ManualIngredientRow = { name: string; menge: string; einheit: string }

function ManualEntryForm({ onAdded }: { onAdded: (entry: CookbookEntry) => void }) {
  const [name, setName] = useState('')
  const [cuisine, setCuisine] = useState('')
  const [cookTime, setCookTime] = useState('')
  const [ingredients, setIngredients] = useState<ManualIngredientRow[]>([
    { name: '', menge: '', einheit: '' },
  ])
  const [steps, setSteps] = useState('')
  const [tips, setTips] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function updateIngredient(i: number, field: keyof ManualIngredientRow, value: string) {
    setIngredients((prev) => prev.map((row, idx) => (idx === i ? { ...row, [field]: value } : row)))
  }

  async function submit() {
    const trimmedName = name.trim()
    const stepLines = steps.split('\n').map((s) => s.trim()).filter(Boolean)
    if (!trimmedName) {
      setError('Name fehlt')
      return
    }
    if (stepLines.length === 0) {
      setError('Mindestens ein Zubereitungsschritt nötig')
      return
    }
    setLoading(true)
    setError('')
    try {
      const entry = await apiFetch<CookbookEntry>('/recipes/manual', {
        method: 'POST',
        body: {
          name: trimmedName,
          cuisine: cuisine || null,
          cook_time_min: cookTime ? Number(cookTime) : null,
          zutaten: ingredients
            .filter((i) => i.name.trim())
            .map((i) => ({
              name: i.name.trim(),
              menge: i.menge ? Number(i.menge.replace(',', '.')) : null,
              einheit: i.einheit.trim() || null,
            })),
          schritte: stepLines,
          tipps: tips.split('\n').map((t) => t.trim()).filter(Boolean),
        },
      })
      onAdded(entry)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Name des Gerichts"
        className="w-full min-w-0 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
      />
      <div className="flex gap-2">
        <select
          value={cuisine}
          onChange={(e) => setCuisine(e.target.value)}
          className="min-w-0 flex-1 rounded-lg border border-stone-300 px-2 py-2 text-sm"
        >
          <option value="">Kategorie…</option>
          <option value="vegetarisch">vegetarisch</option>
          <option value="vegan">vegan</option>
          <option value="Fisch">Fisch</option>
          <option value="Fleisch">Fleisch</option>
          <option value="gemischt">gemischt</option>
        </select>
        <input
          value={cookTime}
          onChange={(e) => setCookTime(e.target.value.replace(/[^0-9]/g, ''))}
          placeholder="Min."
          inputMode="numeric"
          className="w-16 shrink-0 rounded-lg border border-stone-300 px-2 py-2 text-sm"
        />
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold text-stone-500">Zutaten</p>
        <div className="space-y-2">
          {ingredients.map((row, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <input
                value={row.menge}
                onChange={(e) => updateIngredient(i, 'menge', e.target.value)}
                placeholder="Menge"
                className="w-14 min-w-0 shrink-0 rounded-lg border border-stone-300 px-2 py-2 text-sm"
              />
              <input
                value={row.einheit}
                onChange={(e) => updateIngredient(i, 'einheit', e.target.value)}
                placeholder="Einh."
                className="w-14 min-w-0 shrink-0 rounded-lg border border-stone-300 px-2 py-2 text-sm"
              />
              <input
                value={row.name}
                onChange={(e) => updateIngredient(i, 'name', e.target.value)}
                placeholder="Zutat"
                className="min-w-0 flex-1 rounded-lg border border-stone-300 px-2 py-2 text-sm"
              />
              <button
                onClick={() => setIngredients((prev) => prev.filter((_, idx) => idx !== i))}
                aria-label="Zeile entfernen"
                className="shrink-0 p-2 text-stone-300 hover:text-red-500"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <button
          onClick={() => setIngredients((prev) => [...prev, { name: '', menge: '', einheit: '' }])}
          className="mt-2 rounded-lg border border-stone-300 px-3 py-1.5 text-xs text-stone-600 hover:bg-stone-50"
        >
          + Zeile
        </button>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold text-stone-500">Zubereitung (eine Zeile pro Schritt)</p>
        <textarea
          value={steps}
          onChange={(e) => setSteps(e.target.value)}
          rows={5}
          className="w-full min-w-0 resize-y rounded-lg border border-stone-300 p-2 text-sm focus:border-emerald-400 focus:outline-none"
        />
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold text-stone-500">Tipps (optional, eine Zeile pro Tipp)</p>
        <textarea
          value={tips}
          onChange={(e) => setTips(e.target.value)}
          rows={2}
          className="w-full min-w-0 resize-y rounded-lg border border-stone-300 p-2 text-sm focus:border-emerald-400 focus:outline-none"
        />
      </div>

      {error && <p className="rounded bg-red-50 p-2 text-xs text-red-700">{error}</p>}
      <button
        onClick={submit}
        disabled={loading}
        className="min-h-11 w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        {loading ? 'Speichert…' : 'Rezept speichern'}
      </button>
    </div>
  )
}

function AddRecipeDialog({
  onClose,
  onAdded,
}: {
  onClose: () => void
  onAdded: (entry: CookbookEntry) => void
}) {
  const [mode, setMode] = useState<'url' | 'manual'>('url')

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-4 sm:rounded-2xl sm:p-6"
        style={{ paddingBottom: 'max(1rem, env(safe-area-inset-bottom))' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-2">
          <h2 className="min-w-0 truncate font-semibold text-stone-800">Rezept hinzufügen</h2>
          <button
            onClick={onClose}
            aria-label="Schließen"
            className="shrink-0 p-2 text-xl leading-none text-stone-400 hover:text-stone-600"
          >
            ✕
          </button>
        </div>
        <div className="mb-4 flex gap-2">
          <button
            onClick={() => setMode('url')}
            className={`min-h-10 flex-1 rounded-full px-3 py-2 text-sm font-medium transition-colors ${
              mode === 'url' ? 'bg-emerald-600 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
            }`}
          >
            Per Link
          </button>
          <button
            onClick={() => setMode('manual')}
            className={`min-h-10 flex-1 rounded-full px-3 py-2 text-sm font-medium transition-colors ${
              mode === 'manual' ? 'bg-emerald-600 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
            }`}
          >
            Manuell eintragen
          </button>
        </div>
        {mode === 'url' ? <UrlImportForm onAdded={onAdded} /> : <ManualEntryForm onAdded={onAdded} />}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Plan-into-week mini UI inside an expanded card
// ---------------------------------------------------------------------------

function PlanIntoWeekPanel({ entry }: { entry: CookbookEntry }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [week, setWeek] = useState<'current' | 'next'>('current')
  const [cookDay, setCookDay] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [planId, setPlanId] = useState<number | null>(null)

  async function submit() {
    setStatus('loading')
    try {
      const body: Record<string, unknown> = { week }
      if (entry.source === 'eigene') body.saved_recipe_id = entry.saved_recipe_id
      else body.dish_id = entry.dish_id
      if (cookDay) body.cook_day = cookDay
      const res = await apiFetch<{ plan_id: number; message: string }>('/recipes/plan-into-week', {
        method: 'POST',
        body,
      })
      setPlanId(res.plan_id)
      setMessage(res.message)
      setStatus('done')
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Fehler beim Einplanen')
      setStatus('error')
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="min-h-11 rounded-lg border border-emerald-300 px-3 py-2 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
      >
        📅 Einplanen
      </button>
    )
  }

  return (
    <div className="w-full rounded-lg border border-stone-200 bg-stone-50 p-3">
      {status === 'done' ? (
        <div className="text-sm text-emerald-700">
          <p>{message}</p>
          {planId && (
            <button
              onClick={() => navigate(`/plan/${planId}`)}
              className="mt-2 font-medium underline hover:text-emerald-800"
            >
              Zum Wochenplan →
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="mb-2 flex gap-2">
            <button
              onClick={() => setWeek('current')}
              className={`min-h-9 flex-1 rounded-full px-2 py-1.5 text-xs font-medium ${
                week === 'current' ? 'bg-emerald-600 text-white' : 'bg-white text-stone-600 border border-stone-300'
              }`}
            >
              Diese Woche
            </button>
            <button
              onClick={() => setWeek('next')}
              className={`min-h-9 flex-1 rounded-full px-2 py-1.5 text-xs font-medium ${
                week === 'next' ? 'bg-emerald-600 text-white' : 'bg-white text-stone-600 border border-stone-300'
              }`}
            >
              Nächste Woche
            </button>
          </div>
          <select
            value={cookDay}
            onChange={(e) => setCookDay(e.target.value)}
            className="mb-2 w-full min-w-0 rounded-lg border border-stone-300 px-2 py-2 text-xs"
          >
            <option value="">Wochentag (optional)</option>
            {DAYS.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          {status === 'error' && <p className="mb-2 rounded bg-red-50 p-2 text-xs text-red-700">{message}</p>}
          <div className="flex gap-2">
            <button
              onClick={() => setOpen(false)}
              className="min-h-9 rounded-lg border border-stone-300 px-3 py-1.5 text-xs text-stone-500 hover:bg-white"
            >
              Abbrechen
            </button>
            <button
              onClick={submit}
              disabled={status === 'loading'}
              className="min-h-9 flex-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {status === 'loading' ? 'Wird eingeplant…' : 'Bestätigen'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Cookbook() {
  const [entries, setEntries] = useState<CookbookEntry[] | null>(null)
  const [query, setQuery] = useState('')
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [openKey, setOpenKey] = useState<string | null>(null)
  const [pinnedKey, setPinnedKey] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [showAddDialog, setShowAddDialog] = useState(false)
  const itemRefs = useRef<Record<string, HTMLDivElement | null>>({})

  const reload = useCallback(() => {
    const params = new URLSearchParams()
    if (query.trim()) params.set('q', query.trim())
    if (favoritesOnly) params.set('favorites_only', 'true')
    const qs = params.toString()
    setError('')
    apiFetch<CookbookEntry[]>(`/recipes${qs ? `?${qs}` : ''}`)
      .then(setEntries)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Fehler beim Laden'))
  }, [query, favoritesOnly])

  useEffect(() => {
    reload()
  }, [reload])

  const displayEntries = useMemo(() => {
    if (!entries || !pinnedKey) return entries
    const pinned = entries.find((e) => cookbookEntryKey(e) === pinnedKey)
    if (!pinned) return entries
    return [pinned, ...entries.filter((e) => cookbookEntryKey(e) !== pinnedKey)]
  }, [entries, pinnedKey])

  function openCard(key: string) {
    if (openKey === key) {
      setOpenKey(null)
      setPinnedKey(null)
      return
    }
    setOpenKey(key)
    setPinnedKey(key)
    requestAnimationFrame(() => {
      itemRefs.current[key]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  function patchEntry(key: string, changes: Partial<CookbookEntry>) {
    setEntries((prev) => prev?.map((e) => (cookbookEntryKey(e) === key ? { ...e, ...changes } : e)) ?? prev)
  }

  async function toggleFavorite(entry: CookbookEntry) {
    const key = cookbookEntryKey(entry)
    const next = !entry.is_favorite
    patchEntry(key, { is_favorite: next })
    try {
      if (entry.source === 'eigene') {
        await apiFetch(`/recipes/saved/${entry.saved_recipe_id}`, {
          method: 'PATCH',
          body: { is_favorite: next },
        })
      } else {
        await apiFetch(`/plans/${entry.plan_id}/dishes/${entry.dish_id}/feedback`, {
          method: 'PATCH',
          body: { is_favorite: next },
        })
      }
    } catch {
      patchEntry(key, { is_favorite: !next })
    }
  }

  async function setThumbs(entry: CookbookEntry, thumbs: number) {
    if (entry.source !== 'gekocht') return
    const key = cookbookEntryKey(entry)
    const prevThumbs = entry.feedback_thumbs
    patchEntry(key, { feedback_thumbs: thumbs })
    try {
      await apiFetch(`/plans/${entry.plan_id}/dishes/${entry.dish_id}/feedback`, {
        method: 'PATCH',
        body: { thumbs },
      })
    } catch {
      patchEntry(key, { feedback_thumbs: prevThumbs })
    }
  }

  async function deleteSaved(entry: CookbookEntry) {
    if (entry.source !== 'eigene') return
    if (!confirm(`"${entry.name}" wirklich löschen?`)) return
    const key = cookbookEntryKey(entry)
    setEntries((prev) => prev?.filter((e) => cookbookEntryKey(e) !== key) ?? prev)
    if (openKey === key) {
      setOpenKey(null)
      setPinnedKey(null)
    }
    try {
      await apiFetch(`/recipes/saved/${entry.saved_recipe_id}`, { method: 'DELETE' })
    } catch {
      reload()
    }
  }

  function handleAdded(entry: CookbookEntry) {
    setEntries((prev) => (prev ? [entry, ...prev] : [entry]))
    setShowAddDialog(false)
    const key = cookbookEntryKey(entry)
    setOpenKey(key)
    setPinnedKey(key)
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-5 sm:p-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">Unsere Rezepte</h1>
          <p className="mt-1 text-sm text-stone-500">Alle Gerichte, die ihr schon gekocht oder gespeichert habt.</p>
        </div>
        <button
          onClick={() => setShowAddDialog(true)}
          className="min-h-11 shrink-0 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          + Rezept
        </button>
      </header>

      <div className="mb-4 flex flex-wrap gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Rezept suchen…"
          className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
        />
        <button
          onClick={() => setFavoritesOnly((v) => !v)}
          className={`shrink-0 rounded-lg border px-3 py-2 text-sm transition-colors ${
            favoritesOnly
              ? 'border-amber-300 bg-amber-50 text-amber-700'
              : 'border-stone-300 text-stone-500 hover:bg-stone-50'
          }`}
          title="Nur Favoriten anzeigen"
        >
          {favoritesOnly ? '★' : '☆'} Favoriten
        </button>
      </div>

      {error && <p className="mb-3 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      {entries === null && !error && (
        <p className="py-12 text-center text-sm text-stone-400">Lädt…</p>
      )}

      {entries !== null && entries.length === 0 && (
        <div className="rounded-xl border border-stone-200 bg-white p-8 text-center">
          <p className="text-sm text-stone-500">
            {query || favoritesOnly
              ? 'Keine Rezepte gefunden.'
              : 'Noch keine Rezepte — bestätige deinen ersten Wochenplan oder füge eins hinzu.'}
          </p>
        </div>
      )}

      {displayEntries !== null && displayEntries !== undefined && displayEntries.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {displayEntries.map((entry) => {
            const key = cookbookEntryKey(entry)
            const isOpen = openKey === key
            return (
              <div
                key={key}
                ref={(el) => { itemRefs.current[key] = el }}
                className={`overflow-hidden rounded-xl border bg-white transition-all ${
                  isOpen ? 'border-emerald-300 sm:col-span-2' : 'border-stone-200'
                }`}
              >
                <div className="relative">
                  <button onClick={() => openCard(key)} className="block w-full text-left">
                    <DishImage
                      imageUrl={entry.image_url}
                      name={entry.name}
                      cuisine={entry.cuisine}
                      className={isOpen ? 'h-40' : 'h-24'}
                    />
                  </button>
                  <button
                    onClick={() => toggleFavorite(entry)}
                    title={entry.is_favorite ? 'Aus Favoriten entfernen' : 'Als Favorit merken'}
                    className={`absolute right-2 top-2 flex h-9 w-9 items-center justify-center rounded-full bg-white/90 text-lg leading-none shadow-sm ${
                      entry.is_favorite ? 'text-amber-400' : 'text-stone-300 hover:text-stone-400'
                    }`}
                  >
                    {entry.is_favorite ? '★' : '☆'}
                  </button>
                </div>

                <button onClick={() => openCard(key)} className="block w-full text-left">
                  <div className="p-3">
                    <div className="mb-1 flex items-start justify-between gap-1">
                      <span className="min-w-0 line-clamp-2 text-sm font-semibold leading-tight text-stone-800">
                        {entry.name}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {entry.source === 'eigene' && (
                        <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-700">
                          Eigenes
                        </span>
                      )}
                      {entry.cuisine && (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${cuisineBadgeClass(entry.cuisine)}`}
                        >
                          {entry.cuisine}
                        </span>
                      )}
                      {entry.cook_time_min && (
                        <span className="text-xs text-stone-400">{entry.cook_time_min} Min.</span>
                      )}
                    </div>
                  </div>
                </button>

                {isOpen && entry.recipe && (
                  <div className="border-t border-stone-100 p-4 text-sm">
                    <RecipeDetails recipe={entry.recipe} />

                    <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-stone-100 pt-3">
                      {entry.source === 'gekocht' && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-stone-400">Wie war's?</span>
                          <button
                            onClick={() => setThumbs(entry, 1)}
                            className={`min-h-9 min-w-9 rounded-full px-2.5 py-1.5 text-sm ${
                              entry.feedback_thumbs === 1 ? 'bg-emerald-500 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
                            }`}
                          >
                            👍
                          </button>
                          <button
                            onClick={() => setThumbs(entry, -1)}
                            className={`min-h-9 min-w-9 rounded-full px-2.5 py-1.5 text-sm ${
                              entry.feedback_thumbs === -1 ? 'bg-red-400 text-white' : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
                            }`}
                          >
                            👎
                          </button>
                        </div>
                      )}
                      <PlanIntoWeekPanel entry={entry} />
                      {entry.source === 'eigene' && (
                        <button
                          onClick={() => deleteSaved(entry)}
                          className="ml-auto min-h-9 rounded-lg border border-red-200 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50"
                        >
                          Löschen
                        </button>
                      )}
                    </div>
                  </div>
                )}
                {isOpen && !entry.recipe && (
                  <div className="border-t border-stone-100 p-4 text-sm text-stone-400">
                    Kein Rezept verfügbar.
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showAddDialog && (
        <AddRecipeDialog onClose={() => setShowAddDialog(false)} onAdded={handleAdded} />
      )}
    </main>
  )
}
