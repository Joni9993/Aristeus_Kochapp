import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../api/client'
import FeedbackRow from '../components/FeedbackRow'
import type { Plan } from '../types'

function formatWeekRange(startIso: string): string {
  const start = new Date(startIso)
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  const fmt = (d: Date) => d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
  return `${fmt(start)} – ${fmt(end)}`
}

export default function PlanFeedback() {
  const { planId } = useParams<{ planId: string }>()
  const navigate = useNavigate()
  const [plan, setPlan] = useState<Plan | null>(null)
  const [loading, setLoading] = useState(true)
  const [rated, setRated] = useState<Set<number>>(new Set())

  useEffect(() => {
    apiFetch<Plan>(`/plans/${planId}`)
      .then((p) => {
        setPlan(p)
        setRated(
          new Set(
            (p.dishes || [])
              .filter((d) => d.dish_status === 'confirmed' && d.feedback_thumbs !== null)
              .map((d) => d.id)
          )
        )
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [planId])

  const dishes = useMemo(
    () => (plan?.dishes || []).filter((d) => d.dish_status === 'confirmed'),
    [plan]
  )

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

  const progressPct = dishes.length ? (rated.size / dishes.length) * 100 : 0

  return (
    <main className="mx-auto max-w-xl px-4 py-5 sm:p-6">
      <div className="mb-6 border-b border-honey/30 pb-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">Wie war eure Woche?</h1>
        <p className="mt-1 text-sm text-muted">{formatWeekRange(plan.week_start_date)}</p>
      </div>

      <div className="mb-6">
        <div className="mb-1 text-xs text-muted">
          {rated.size} von {dishes.length} bewertet
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-olive-soft">
          <div
            className="h-full rounded-full bg-olive transition-all"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {dishes.length === 0 && (
        <p className="text-sm text-muted">Keine Gerichte in dieser Woche.</p>
      )}

      <div className="space-y-4">
        {dishes.map((d) => (
          <div key={d.id} className="rounded-xl border border-line bg-card p-4">
            <div className="mb-1 flex min-w-0 items-baseline gap-2">
              <span className="min-w-0 truncate font-display font-medium text-ink">{d.name}</span>
              {d.cook_day && <span className="shrink-0 text-xs text-muted">{d.cook_day}</span>}
            </div>
            <FeedbackRow
              planId={plan.id}
              dish={d}
              onThumbsChange={(id) => setRated((prev) => new Set(prev).add(id))}
            />
          </div>
        ))}
      </div>

      {/* Sticky so "Fertig" stays reachable without scrolling back up after
          rating many dishes. */}
      <div
        className="sticky z-20 -mx-4 mt-6 border-t border-line bg-card/90 px-4 pt-3 backdrop-blur sm:-mx-6 sm:px-6"
        style={{ bottom: 'calc(6rem + env(safe-area-inset-bottom))', paddingBottom: '0.75rem' }}
      >
        <button
          onClick={() => navigate('/')}
          className="w-full rounded-lg bg-olive py-3 text-sm font-semibold text-olive-on hover:bg-olive-hover"
        >
          Fertig
        </button>
      </div>
    </main>
  )
}
