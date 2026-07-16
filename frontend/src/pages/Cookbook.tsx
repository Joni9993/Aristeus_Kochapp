import { useEffect, useState } from 'react'
import { apiFetch, ApiError } from '../api/client'
import DishImage from '../components/DishImage'
import RecipeDetails from '../components/RecipeDetails'
import { cuisineBadgeClass } from '../types'
import type { CookbookEntry } from '../types'

export default function Cookbook() {
  const [entries, setEntries] = useState<CookbookEntry[] | null>(null)
  const [query, setQuery] = useState('')
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const params = new URLSearchParams()
    if (query.trim()) params.set('q', query.trim())
    if (favoritesOnly) params.set('favorites_only', 'true')
    const qs = params.toString()
    setError('')
    apiFetch<CookbookEntry[]>(`/recipes${qs ? `?${qs}` : ''}`)
      .then(setEntries)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Fehler beim Laden'))
  }, [query, favoritesOnly])

  return (
    <main className="mx-auto max-w-xl p-6 pb-24">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Unsere Rezepte</h1>
        <p className="mt-1 text-sm text-stone-500">Alle Gerichte, die ihr schon gekocht habt.</p>
      </header>

      <div className="mb-4 flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Rezept suchen…"
          className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
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
              : 'Noch keine Rezepte — bestätige deinen ersten Wochenplan.'}
          </p>
        </div>
      )}

      {entries !== null && entries.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          {entries.map((entry) => {
            const isOpen = open === entry.dish_id
            return (
              <div
                key={entry.dish_id}
                className={`overflow-hidden rounded-xl border bg-white transition-all ${
                  isOpen ? 'col-span-2 border-emerald-300' : 'border-stone-200'
                }`}
              >
                <button
                  onClick={() => setOpen(isOpen ? null : entry.dish_id)}
                  className="block w-full text-left"
                >
                  <DishImage
                    imageUrl={entry.image_url}
                    name={entry.name}
                    cuisine={entry.cuisine}
                    className={isOpen ? 'h-40' : 'h-24'}
                  />
                  <div className="p-3">
                    <div className="mb-1 flex items-start justify-between gap-1">
                      <span className="text-sm font-semibold leading-tight text-stone-800">
                        {entry.name}
                      </span>
                      {entry.is_favorite && <span className="shrink-0 text-amber-400">★</span>}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
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
    </main>
  )
}
