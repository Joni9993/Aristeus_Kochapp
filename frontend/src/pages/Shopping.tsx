// Standalone "Einkauf" tab (task 6) — a compact plan picker above the full
// shopping list of the selected plan. Reuses the same ShoppingView component
// Plan.tsx embeds as one of its two tabs, so there's exactly one
// implementation of the list/poll/add-item logic.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiFetch, ApiError } from '../api/client'
import ShoppingView from '../components/ShoppingView'
import type { Plan, ShoppingItem } from '../types'

type PlanSummary = {
  id: number
  week_start_date: string
  status: string
}

function formatWeekRange(startIso: string): string {
  const start = new Date(startIso + 'T00:00:00')
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  const fmt = (d: Date) => d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
  return `KW ${fmt(start)}–${fmt(end)}`
}

function isCurrentWeek(startIso: string): boolean {
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const start = new Date(startIso + 'T00:00:00')
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  return now >= start && now <= end
}

export default function Shopping() {
  const [summaries, setSummaries] = useState<PlanSummary[] | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [error, setError] = useState('')

  const eligible = useMemo(
    () => (summaries || []).filter((p) => p.status === 'confirmed' || p.status === 'complete'),
    [summaries]
  )

  useEffect(() => {
    apiFetch<PlanSummary[]>('/plans')
      .then((all) => {
        setSummaries(all)
        const withShopping = all.filter((p) => p.status === 'confirmed' || p.status === 'complete')
        const current = withShopping.find((p) => isCurrentWeek(p.week_start_date))
        const preselect = current || withShopping[0] || null
        if (preselect) setSelectedId(preselect.id)
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Fehler beim Laden'))
  }, [])

  useEffect(() => {
    if (selectedId == null) {
      setPlan(null)
      return
    }
    apiFetch<Plan>(`/plans/${selectedId}`)
      .then(setPlan)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Fehler beim Laden'))
  }, [selectedId])

  function updateShoppingItem(id: number, changes: Partial<ShoppingItem>) {
    setPlan((prev) =>
      prev
        ? { ...prev, shopping_items: prev.shopping_items?.map((i) => (i.id === id ? { ...i, ...changes } : i)) }
        : prev
    )
  }

  function addShoppingItem(item: ShoppingItem) {
    setPlan((prev) => (prev ? { ...prev, shopping_items: [...(prev.shopping_items || []), item] } : prev))
  }

  function removeShoppingItem(id: number) {
    setPlan((prev) =>
      prev ? { ...prev, shopping_items: (prev.shopping_items || []).filter((i) => i.id !== id) } : prev
    )
  }

  const syncShoppingItems = useCallback((items: ShoppingItem[]) => {
    setPlan((prev) => (prev ? { ...prev, shopping_items: items } : prev))
  }, [])

  return (
    <main className="mx-auto max-w-xl px-4 py-5 sm:p-6">
      <header className="mb-6 border-b border-honey/30 pb-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">Einkaufsliste</h1>
      </header>

      {error && <p className="mb-3 rounded bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">{error}</p>}

      {summaries === null && !error && (
        <p className="py-12 text-center text-sm text-muted">Lädt…</p>
      )}

      {summaries !== null && eligible.length === 0 && (
        <div className="rounded-2xl border border-line bg-card p-8 text-center">
          <p className="text-sm text-muted">
            Noch keine Einkaufsliste — bestätige zuerst einen Wochenplan.
          </p>
        </div>
      )}

      {eligible.length > 0 && (
        <>
          <div className="mb-5 flex flex-wrap gap-2">
            {eligible.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelectedId(p.id)}
                className={`shrink-0 rounded-full px-3 py-2 text-sm font-medium transition-colors ${
                  selectedId === p.id
                    ? 'bg-olive text-olive-on'
                    : 'bg-olive-soft text-ink hover:bg-line'
                }`}
              >
                {formatWeekRange(p.week_start_date)}
              </button>
            ))}
          </div>

          {plan ? (
            <ShoppingView
              plan={plan}
              onItemUpdate={updateShoppingItem}
              onItemAdded={addShoppingItem}
              onItemRemoved={removeShoppingItem}
              onSync={syncShoppingItems}
            />
          ) : (
            <p className="py-12 text-center text-sm text-muted">Lädt…</p>
          )}
        </>
      )}
    </main>
  )
}
