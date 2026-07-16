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

  const progressPct = dishes.length ? (rated.size / dishes.length) * 100 : 0

  return (
    <main className="mx-auto max-w-xl p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Wie war eure Woche?</h1>
        <p className="mt-1 text-sm text-stone-500">{formatWeekRange(plan.week_start_date)}</p>
      </div>

      <div className="mb-6">
        <div className="mb-1 text-xs text-stone-500">
          {rated.size} von {dishes.length} bewertet
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-stone-100">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {dishes.length === 0 && (
        <p className="text-sm text-stone-400">Keine Gerichte in dieser Woche.</p>
      )}

      <div className="space-y-4">
        {dishes.map((d) => (
          <div key={d.id} className="rounded-xl border border-stone-200 bg-white p-4">
            <div className="mb-1 flex items-center gap-2">
              <span className="font-medium text-stone-800">{d.name}</span>
              {d.cook_day && <span className="text-xs text-stone-400">{d.cook_day}</span>}
            </div>
            <FeedbackRow
              planId={plan.id}
              dish={d}
              onThumbsChange={(id) => setRated((prev) => new Set(prev).add(id))}
            />
          </div>
        ))}
      </div>

      <button
        onClick={() => navigate('/')}
        className="mt-6 w-full rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-700"
      >
        Fertig
      </button>
    </main>
  )
}
